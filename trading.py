"""
AI-powered trading module for IBKR Client Portal API.

Places and manages orders through the Interactive Brokers gateway,
with AI-driven trade recommendations derived from the ai_analyst
analysis pipeline. All trades require explicit user confirmation.
"""
import logging
import re
from datetime import datetime, timezone

from ibkr_client import (
    IBKR_BASE_URL,
    REQUEST_TIMEOUT,
    _get,
    _post,
    _session,
    get_account_summary,
    get_positions,
    search_contract,
)

logger = logging.getLogger("trading")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_SIDES = ("BUY", "SELL")
VALID_ORDER_TYPES = ("MKT", "LMT", "STP", "STP_LIMIT")
VALID_TIF_VALUES = ("DAY", "GTC", "IOC", "OPG")
MAX_POSITION_SIZE_PCT = 0.10  # 10% of portfolio value
MIN_QUANTITY = 1
MAX_QUANTITY = 100_000
CONFIRMATION_TIMEOUT = 10  # seconds for reply endpoint


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------

def _validate_order_params(account_id, conid, side, quantity, order_type, price, tif):
    """Validate all order parameters before submission.

    Raises ValueError with a descriptive message on invalid input.
    """
    if not account_id or not isinstance(account_id, str):
        raise ValueError("account_id must be a non-empty string")

    if not conid:
        raise ValueError("conid must be a valid contract identifier")

    side_upper = side.upper() if isinstance(side, str) else ""
    if side_upper not in VALID_SIDES:
        raise ValueError(
            f"side must be one of {VALID_SIDES}, got '{side}'"
        )

    if not isinstance(quantity, (int, float)) or quantity < MIN_QUANTITY:
        raise ValueError(
            f"quantity must be a positive number >= {MIN_QUANTITY}, got {quantity}"
        )

    if quantity > MAX_QUANTITY:
        raise ValueError(
            f"quantity exceeds maximum of {MAX_QUANTITY}, got {quantity}"
        )

    order_upper = order_type.upper() if isinstance(order_type, str) else ""
    if order_upper not in VALID_ORDER_TYPES:
        raise ValueError(
            f"order_type must be one of {VALID_ORDER_TYPES}, got '{order_type}'"
        )

    if order_upper in ("LMT", "STP", "STP_LIMIT") and price is None:
        raise ValueError(
            f"price is required for order_type '{order_upper}'"
        )

    if price is not None and (not isinstance(price, (int, float)) or price <= 0):
        raise ValueError(f"price must be a positive number, got {price}")

    tif_upper = tif.upper() if isinstance(tif, str) else ""
    if tif_upper not in VALID_TIF_VALUES:
        raise ValueError(
            f"tif must be one of {VALID_TIF_VALUES}, got '{tif}'"
        )


def _validate_account_id(account_id):
    """Validate account ID format (alphanumeric)."""
    if not account_id or not re.match(r'^[A-Za-z0-9]+$', account_id):
        raise ValueError(f"Invalid account_id format: '{account_id}'")


# ---------------------------------------------------------------------------
# HTTP DELETE helper (not in ibkr_client.py)
# ---------------------------------------------------------------------------

def _delete(endpoint):
    """Make a DELETE request to the IBKR gateway."""
    url = f"{IBKR_BASE_URL}{endpoint}"
    try:
        resp = _session.delete(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("IBKR DELETE request failed %s: %s", endpoint, exc)
        return None


# ---------------------------------------------------------------------------
# Order Confirmation Reply
# ---------------------------------------------------------------------------

def _confirm_order_reply(reply_id):
    """Reply to IBKR order confirmation prompt.

    The Client Portal API requires a second POST to confirm
    certain orders. This sends the confirmation automatically
    after the initial order submission.
    """
    if not reply_id:
        return None

    logger.info("Confirming order reply_id=%s", reply_id)
    result = _post(
        f"/iserver/reply/{reply_id}",
        data={"confirmed": True},
    )
    return result


# ---------------------------------------------------------------------------
# Order Placement
# ---------------------------------------------------------------------------

def place_order(account_id, conid, side, quantity, order_type, price=None, tif="DAY"):
    """Place an equity order via IBKR Client Portal API.

    Args:
        account_id: IBKR account identifier.
        conid: Contract ID for the instrument.
        side: "BUY" or "SELL".
        quantity: Number of shares.
        order_type: "MKT", "LMT", "STP", or "STP_LIMIT".
        price: Limit or stop price (required for LMT/STP/STP_LIMIT).
        tif: Time in force -- "DAY", "GTC", "IOC", or "OPG".

    Returns:
        Dict with order status and details, or error information.
    """
    _validate_account_id(account_id)
    _validate_order_params(account_id, conid, side, quantity, order_type, price, tif)

    side_upper = side.upper()
    order_upper = order_type.upper()
    tif_upper = tif.upper()

    order_body = {
        "orders": [
            {
                "conid": int(conid),
                "orderType": order_upper,
                "side": side_upper,
                "quantity": int(quantity),
                "tif": tif_upper,
            }
        ]
    }

    if price is not None and order_upper in ("LMT", "STP_LIMIT"):
        order_body["orders"][0]["price"] = float(price)

    if price is not None and order_upper in ("STP", "STP_LIMIT"):
        order_body["orders"][0]["auxPrice"] = float(price)

    logger.info(
        "Placing order: account=%s conid=%s side=%s qty=%s type=%s price=%s tif=%s",
        account_id, conid, side_upper, quantity, order_upper, price, tif_upper,
    )

    result = _post(
        f"/iserver/account/{account_id}/orders",
        data=order_body,
    )

    if not result:
        logger.error("Order submission failed -- no response from gateway")
        return {
            "success": False,
            "error": "No response from IBKR gateway",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return _handle_order_response(result)


def place_option_order(account_id, conid, side, quantity, order_type, price=None, tif="DAY"):
    """Place an options order via IBKR Client Portal API.

    Identical interface to place_order but for options contracts.
    The conid should reference a specific option contract
    (resolved via ibkr_client.get_option_contracts).

    Args:
        account_id: IBKR account identifier.
        conid: Contract ID for the specific option contract.
        side: "BUY" or "SELL".
        quantity: Number of contracts.
        order_type: "MKT", "LMT", "STP", or "STP_LIMIT".
        price: Limit or stop price (required for LMT/STP/STP_LIMIT).
        tif: Time in force -- "DAY", "GTC", "IOC", or "OPG".

    Returns:
        Dict with order status and details, or error information.
    """
    _validate_account_id(account_id)
    _validate_order_params(account_id, conid, side, quantity, order_type, price, tif)

    side_upper = side.upper()
    order_upper = order_type.upper()
    tif_upper = tif.upper()

    order_body = {
        "orders": [
            {
                "conid": int(conid),
                "secType": "OPT",
                "orderType": order_upper,
                "side": side_upper,
                "quantity": int(quantity),
                "tif": tif_upper,
            }
        ]
    }

    if price is not None and order_upper in ("LMT", "STP_LIMIT"):
        order_body["orders"][0]["price"] = float(price)

    if price is not None and order_upper in ("STP", "STP_LIMIT"):
        order_body["orders"][0]["auxPrice"] = float(price)

    logger.info(
        "Placing option order: account=%s conid=%s side=%s qty=%s type=%s price=%s tif=%s",
        account_id, conid, side_upper, quantity, order_upper, price, tif_upper,
    )

    result = _post(
        f"/iserver/account/{account_id}/orders",
        data=order_body,
    )

    if not result:
        logger.error("Option order submission failed -- no response from gateway")
        return {
            "success": False,
            "error": "No response from IBKR gateway",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return _handle_order_response(result)


def _handle_order_response(result):
    """Process IBKR order response, handling confirmation prompts.

    The IBKR Client Portal API may return a confirmation requirement
    (with a reply_id) that must be acknowledged before the order
    is finalized.

    Returns:
        Dict with order outcome including status and order_id.
    """
    # The response can be a list of message/confirmation objects
    if isinstance(result, list):
        for item in result:
            reply_id = item.get("id")
            if reply_id:
                logger.info(
                    "Order requires confirmation: %s",
                    item.get("message", "No message"),
                )
                confirm_result = _confirm_order_reply(reply_id)
                if confirm_result:
                    return _parse_confirmed_response(confirm_result)

                return {
                    "success": False,
                    "error": "Confirmation reply failed",
                    "confirmation_message": item.get("message"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        # List without reply_id means direct order confirmation
        return _parse_confirmed_response(result)

    # Single dict response -- check for order_id or error
    if isinstance(result, dict):
        if "error" in result:
            logger.error("Order rejected: %s", result["error"])
            return {
                "success": False,
                "error": result["error"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        return _parse_confirmed_response(result)

    return {
        "success": False,
        "error": "Unexpected response format",
        "raw_response": str(result),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _parse_confirmed_response(result):
    """Extract order details from a confirmed order response."""
    timestamp = datetime.now(timezone.utc).isoformat()

    if isinstance(result, list) and len(result) > 0:
        first = result[0]
        order_id = first.get("order_id") or first.get("orderId")
        order_status = first.get("order_status") or first.get("orderStatus", "Submitted")
        return {
            "success": True,
            "order_id": order_id,
            "order_status": order_status,
            "timestamp": timestamp,
            "details": first,
        }

    if isinstance(result, dict):
        order_id = result.get("order_id") or result.get("orderId")
        order_status = result.get("order_status") or result.get("orderStatus", "Submitted")
        return {
            "success": True,
            "order_id": order_id,
            "order_status": order_status,
            "timestamp": timestamp,
            "details": result,
        }

    return {
        "success": True,
        "order_id": None,
        "order_status": "Unknown",
        "timestamp": timestamp,
        "raw_response": str(result),
    }


# ---------------------------------------------------------------------------
# Order Management
# ---------------------------------------------------------------------------

def get_order_status(order_id):
    """Check status of a specific order by scanning live orders.

    Args:
        order_id: The order ID returned from place_order.

    Returns:
        Dict with order status details, or None if not found.
    """
    if not order_id:
        return {"error": "order_id is required"}

    orders = get_live_orders()
    if not orders or "orders" not in orders:
        return {"error": "Could not retrieve orders", "order_id": order_id}

    for order in orders.get("orders", []):
        found_id = order.get("orderId") or order.get("order_id")
        if str(found_id) == str(order_id):
            return {
                "order_id": order_id,
                "status": order.get("status", "Unknown"),
                "filled_quantity": order.get("filledQuantity", 0),
                "remaining_quantity": order.get("remainingQuantity", 0),
                "avg_fill_price": order.get("avgPrice"),
                "side": order.get("side"),
                "order_type": order.get("orderType"),
                "ticker": order.get("ticker"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw": order,
            }

    return {
        "order_id": order_id,
        "status": "NotFound",
        "message": "Order not found in live orders -- may be filled or cancelled",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_live_orders():
    """Retrieve all live/working orders.

    Returns:
        Dict with 'orders' key containing list of active orders,
        or error dict on failure.
    """
    result = _get("/iserver/account/orders")
    if result is None:
        return {"error": "Could not retrieve live orders", "orders": []}
    return result


def cancel_order(account_id, order_id):
    """Cancel an open order.

    Args:
        account_id: IBKR account identifier.
        order_id: The order ID to cancel.

    Returns:
        Dict with cancellation result.
    """
    _validate_account_id(account_id)
    if not order_id:
        return {"success": False, "error": "order_id is required"}

    logger.info("Cancelling order: account=%s order_id=%s", account_id, order_id)

    result = _delete(f"/iserver/account/{account_id}/order/{order_id}")
    if result is None:
        return {
            "success": False,
            "error": "Cancel request failed -- no response from gateway",
            "order_id": order_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "success": True,
        "order_id": order_id,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# AI Trade Recommendation
# ---------------------------------------------------------------------------

def ai_trade_recommendation(ticker, analysis_result):
    """Generate a structured trade recommendation from AI analysis.

    Translates the output of ai_analyst.analyze_stock() into an
    actionable trade recommendation with risk management parameters.

    Args:
        ticker: Stock ticker symbol.
        analysis_result: Dict from ai_analyst.analyze_stock() containing
            rating, confidence, price_targets, position_sizing,
            entry_strategy, exit_strategy, etc.

    Returns:
        Dict with trade recommendation. Always includes
        requires_confirmation=True as a safety measure.
    """
    if not ticker:
        return {"error": "ticker is required", "requires_confirmation": True}

    if not analysis_result or "error" in analysis_result:
        return {
            "action": "HOLD",
            "ticker": ticker,
            "error": analysis_result.get("error", "No analysis available"),
            "reasoning": "Cannot generate recommendation without valid analysis",
            "requires_confirmation": True,
        }

    rating = analysis_result.get("rating", "HOLD")
    confidence = analysis_result.get("confidence", 5)
    price_targets = analysis_result.get("price_targets", {})
    position_sizing_raw = analysis_result.get("position_sizing", "2%")

    action = _map_rating_to_action(rating)
    limit_price = _extract_limit_price(price_targets, action)
    stop_loss = _extract_stop_loss(price_targets, action)
    take_profit = _extract_take_profit(price_targets, action)
    quantity_suggestion = _parse_position_sizing(position_sizing_raw)
    risk_reward = _calculate_risk_reward(limit_price, stop_loss, take_profit)

    reasoning_parts = []
    summary = analysis_result.get("summary", "")
    if summary:
        reasoning_parts.append(summary)

    entry_strategy = analysis_result.get("entry_strategy", "")
    if entry_strategy:
        reasoning_parts.append(f"Entry: {entry_strategy}")

    exit_strategy = analysis_result.get("exit_strategy", "")
    if exit_strategy:
        reasoning_parts.append(f"Exit: {exit_strategy}")

    reasoning = " | ".join(reasoning_parts) if reasoning_parts else "See full analysis"

    order_type = "LMT" if limit_price else "MKT"

    recommendation = {
        "action": action,
        "ticker": ticker,
        "order_type": order_type,
        "limit_price": limit_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "quantity_suggestion": quantity_suggestion,
        "risk_reward_ratio": risk_reward,
        "confidence": confidence,
        "reasoning": reasoning,
        "requires_confirmation": True,
        "rating": rating,
        "price_targets": price_targets,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "AI recommendation for %s: action=%s confidence=%s order_type=%s",
        ticker, action, confidence, order_type,
    )

    return recommendation


def _map_rating_to_action(rating):
    """Map AI analysis rating to a trade action."""
    buy_ratings = ("STRONG_BUY", "BUY")
    sell_ratings = ("STRONG_SELL", "SELL")

    rating_upper = rating.upper() if rating else "HOLD"

    if rating_upper in buy_ratings:
        return "BUY"
    if rating_upper in sell_ratings:
        return "SELL"
    return "HOLD"


def _extract_limit_price(price_targets, action):
    """Derive a limit price from AI price targets.

    For BUY orders, uses the bear_case as an attractive entry.
    For SELL orders, uses the bull_case as an attractive exit.
    """
    if not price_targets:
        return None

    if action == "BUY":
        price = price_targets.get("bear_case") or price_targets.get("base_case")
    elif action == "SELL":
        price = price_targets.get("bull_case") or price_targets.get("base_case")
    else:
        return None

    return _safe_float(price)


def _extract_stop_loss(price_targets, action):
    """Derive a stop-loss level from AI price targets."""
    if not price_targets:
        return None

    if action == "BUY":
        bear = _safe_float(price_targets.get("bear_case"))
        if bear:
            # Stop loss 5% below bear case for buys
            return round(bear * 0.95, 2)
    elif action == "SELL":
        bull = _safe_float(price_targets.get("bull_case"))
        if bull:
            # Stop loss 5% above bull case for sells (short)
            return round(bull * 1.05, 2)

    return None


def _extract_take_profit(price_targets, action):
    """Derive a take-profit level from AI price targets."""
    if not price_targets:
        return None

    if action == "BUY":
        return _safe_float(price_targets.get("bull_case"))
    elif action == "SELL":
        return _safe_float(price_targets.get("bear_case"))

    return None


def _parse_position_sizing(raw_value):
    """Parse position sizing string from AI (e.g. '2%', '2-3%') into a float percentage.

    Returns a float representing the portfolio percentage (e.g. 2.0 for '2%').
    Caps at MAX_POSITION_SIZE_PCT * 100 for safety.
    """
    if isinstance(raw_value, (int, float)):
        return min(float(raw_value), MAX_POSITION_SIZE_PCT * 100)

    if not isinstance(raw_value, str):
        return 2.0  # conservative default

    # Extract first number from strings like "2%", "2-3%", "up to 3%"
    match = re.search(r'(\d+(?:\.\d+)?)', raw_value)
    if match:
        value = float(match.group(1))
        return min(value, MAX_POSITION_SIZE_PCT * 100)

    return 2.0


def _calculate_risk_reward(entry, stop_loss, take_profit):
    """Calculate risk/reward ratio from price levels.

    Returns the ratio as a float (e.g. 2.5 means 2.5:1 reward to risk).
    """
    if not all([entry, stop_loss, take_profit]):
        return None

    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)

    if risk == 0:
        return None

    return round(reward / risk, 2)


def _safe_float(value):
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Trade Execution (with safety gate)
# ---------------------------------------------------------------------------

def execute_ai_trade(account_id, recommendation, confirmed=False):
    """Execute a trade based on an AI recommendation.

    SAFETY: This function will refuse to execute unless confirmed=True.
    The caller (UI or CLI) must obtain explicit user confirmation
    before setting confirmed=True.

    Args:
        account_id: IBKR account identifier.
        recommendation: Dict from ai_trade_recommendation().
        confirmed: Must be True for the trade to execute.

    Returns:
        Dict with execution result or rejection reason.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Gate 1: Explicit confirmation required
    if not confirmed:
        logger.warning(
            "Trade execution blocked -- user confirmation required for %s %s",
            recommendation.get("action"),
            recommendation.get("ticker"),
        )
        return {
            "executed": False,
            "reason": "Trade requires explicit user confirmation. "
                      "Set confirmed=True after user approval.",
            "recommendation": recommendation,
            "timestamp": timestamp,
        }

    # Gate 2: Only execute actionable recommendations
    action = recommendation.get("action", "HOLD")
    if action == "HOLD":
        return {
            "executed": False,
            "reason": "Recommendation is HOLD -- no trade to execute",
            "recommendation": recommendation,
            "timestamp": timestamp,
        }

    # Gate 3: Validate required fields
    ticker = recommendation.get("ticker")
    if not ticker:
        return {
            "executed": False,
            "reason": "No ticker in recommendation",
            "timestamp": timestamp,
        }

    # Gate 4: Position size check against portfolio
    size_check = _check_position_size(account_id, recommendation)
    if not size_check["is_allowed"]:
        logger.warning(
            "Position size check failed for %s: %s",
            ticker, size_check["reason"],
        )
        return {
            "executed": False,
            "reason": size_check["reason"],
            "recommendation": recommendation,
            "timestamp": timestamp,
        }

    # Resolve ticker to conid
    conid = search_contract(ticker)
    if not conid:
        return {
            "executed": False,
            "reason": f"Could not resolve contract for {ticker}",
            "timestamp": timestamp,
        }

    # Build order parameters
    order_type = recommendation.get("order_type", "MKT")
    price = recommendation.get("limit_price")
    quantity = size_check.get("adjusted_quantity", 1)
    side = action
    tif = "DAY"

    logger.info(
        "Executing AI trade: %s %s qty=%s type=%s price=%s",
        side, ticker, quantity, order_type, price,
    )

    # Place the order
    result = place_order(
        account_id=account_id,
        conid=conid,
        side=side,
        quantity=quantity,
        order_type=order_type,
        price=price,
        tif=tif,
    )

    result["recommendation"] = recommendation
    result["executed"] = result.get("success", False)

    logger.info(
        "AI trade result for %s: executed=%s order_id=%s",
        ticker,
        result.get("executed"),
        result.get("order_id"),
    )

    return result


def _check_position_size(account_id, recommendation):
    """Verify that the recommended position does not exceed the max allocation.

    Enforces the MAX_POSITION_SIZE_PCT limit (10% of portfolio).

    Returns dict with is_allowed bool and adjusted_quantity.
    """
    pct = recommendation.get("quantity_suggestion", 2.0)
    max_pct = MAX_POSITION_SIZE_PCT * 100

    if pct > max_pct:
        return {
            "is_allowed": False,
            "reason": (
                f"Recommended allocation {pct}% exceeds maximum "
                f"allowed {max_pct}% of portfolio"
            ),
        }

    # Attempt to calculate share quantity from portfolio value
    summary = get_account_summary(account_id)
    if not summary:
        # Cannot verify -- allow with conservative quantity
        return {
            "is_allowed": True,
            "adjusted_quantity": 1,
            "reason": "Could not fetch account summary -- defaulting to 1 share",
        }

    # Extract net liquidation value
    net_liq = _extract_net_liquidation(summary)
    if not net_liq or net_liq <= 0:
        return {
            "is_allowed": True,
            "adjusted_quantity": 1,
            "reason": "Could not determine portfolio value -- defaulting to 1 share",
        }

    # Calculate max dollar amount for this position
    max_dollars = net_liq * (pct / 100.0)

    # Use limit price or base case price to estimate shares
    price = (
        recommendation.get("limit_price")
        or _safe_float(
            recommendation.get("price_targets", {}).get("base_case")
        )
    )

    if not price or price <= 0:
        return {
            "is_allowed": True,
            "adjusted_quantity": 1,
            "reason": "No price available for quantity calculation -- defaulting to 1 share",
        }

    quantity = int(max_dollars / price)
    quantity = max(quantity, 1)

    return {
        "is_allowed": True,
        "adjusted_quantity": quantity,
        "max_dollars": round(max_dollars, 2),
        "net_liquidation": round(net_liq, 2),
        "allocation_pct": pct,
    }


def _extract_net_liquidation(summary):
    """Extract net liquidation value from account summary response.

    The IBKR account summary can return data in different formats
    depending on the gateway version.
    """
    if not summary:
        return None

    # Direct key access
    if isinstance(summary, dict):
        # Format: {"netliquidation": {"amount": 123456.78}}
        net_liq = summary.get("netliquidation")
        if isinstance(net_liq, dict):
            return _safe_float(net_liq.get("amount"))
        if isinstance(net_liq, (int, float)):
            return float(net_liq)

        # Alternative key names
        for key in ("netLiquidation", "NetLiquidation", "totalcashvalue"):
            val = summary.get(key)
            if isinstance(val, dict):
                return _safe_float(val.get("amount"))
            if isinstance(val, (int, float)):
                return float(val)

    return None


# ---------------------------------------------------------------------------
# Portfolio Summary
# ---------------------------------------------------------------------------

def get_portfolio_summary(account_id):
    """Combine account summary and positions into a unified view.

    Args:
        account_id: IBKR account identifier.

    Returns:
        Dict with account balances, positions, and computed metrics.
    """
    _validate_account_id(account_id)

    summary = get_account_summary(account_id)
    positions = get_positions(account_id)

    net_liq = _extract_net_liquidation(summary) if summary else None

    # Build positions list
    position_list = []
    total_market_value = 0.0
    total_unrealized_pnl = 0.0

    if positions and isinstance(positions, list):
        for pos in positions:
            market_value = _safe_float(pos.get("mktValue", 0)) or 0.0
            unrealized = _safe_float(pos.get("unrealizedPnl", 0)) or 0.0
            quantity = _safe_float(pos.get("position", 0)) or 0.0
            avg_cost = _safe_float(pos.get("avgCost", 0)) or 0.0

            total_market_value += market_value
            total_unrealized_pnl += unrealized

            allocation_pct = None
            if net_liq and net_liq > 0:
                allocation_pct = round((abs(market_value) / net_liq) * 100, 2)

            position_list.append({
                "conid": pos.get("conid"),
                "ticker": pos.get("contractDesc", pos.get("ticker", "Unknown")),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "allocation_pct": allocation_pct,
                "currency": pos.get("currency", "USD"),
            })

    # Sort positions by absolute market value descending
    position_list.sort(key=lambda p: abs(p.get("market_value", 0)), reverse=True)

    return {
        "account_id": account_id,
        "net_liquidation": net_liq,
        "total_market_value": round(total_market_value, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "position_count": len(position_list),
        "positions": position_list,
        "cash_balance": _extract_cash_balance(summary),
        "buying_power": _extract_buying_power(summary),
        "account_summary_raw": summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_cash_balance(summary):
    """Extract cash balance from account summary."""
    if not summary or not isinstance(summary, dict):
        return None

    for key in ("totalcashvalue", "TotalCashValue", "cashbalance"):
        val = summary.get(key)
        if isinstance(val, dict):
            return _safe_float(val.get("amount"))
        if isinstance(val, (int, float)):
            return float(val)

    return None


def _extract_buying_power(summary):
    """Extract buying power from account summary."""
    if not summary or not isinstance(summary, dict):
        return None

    for key in ("buyingpower", "BuyingPower", "availablefunds"):
        val = summary.get(key)
        if isinstance(val, dict):
            return _safe_float(val.get("amount"))
        if isinstance(val, (int, float)):
            return float(val)

    return None
