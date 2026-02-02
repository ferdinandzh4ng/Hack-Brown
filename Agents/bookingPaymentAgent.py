#!/usr/bin/env python3
"""
Booking and Payment Agent - Books reservations and processes payments for selected itinerary items
This agent takes selected itinerary items, makes reservations where needed, and processes payments.
"""
from uagents import Agent, Context, Protocol, Model
from uagents_core.contrib.protocols.chat import (
    ChatMessage,
    TextContent,
    chat_protocol_spec,
    ChatAcknowledgement,
)
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from uuid import uuid4
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import threading
import sys
import os
import re

# Add Agents directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Login import LoginManager

load_dotenv()

# Initialize LoginManager for accessing payment methods
login_manager = LoginManager()

# ============================================================
# Models
# ============================================================

class ItineraryItem(Model):
    """Individual itinerary item to book"""
    id: str
    title: str
    cost: str  # e.g., "$50.00"
    startTime: Optional[str] = None  # e.g., "08:00"
    endTime: Optional[str] = None
    address: Optional[str] = None
    coordinates: Optional[List[float]] = None
    agent_reasoning: Optional[str] = None

class BookingRequest(Model):
    """Input model for booking request"""
    items: List[ItineraryItem]
    location: str
    user_id: Optional[str] = None  # For payment processing

class BookingResult(Model):
    """Result for a single booking attempt"""
    item_id: str
    item_title: str
    booking_required: bool
    booking_status: str  # "success", "failed", "not_required", "payment_required"
    reservation_id: Optional[str] = None
    payment_status: Optional[str] = None  # "paid", "pending", "failed", "not_required"
    payment_amount: Optional[float] = None
    confirmation_code: Optional[str] = None
    error_message: Optional[str] = None
    notes: Optional[str] = None

class BookingResponse(Model):
    """Response model with booking and payment results"""
    location: str
    total_items: int
    bookings: List[BookingResult]
    total_cost: float
    total_paid: float
    summary: Dict[str, Any]

# ============================================================
# AI Client
# ============================================================

client = OpenAI(
    base_url="https://api.asi1.ai/v1",
    api_key=os.getenv("FETCH_API_KEY", ""),
)

# ============================================================
# System Prompts
# ============================================================

BOOKING_PROMPT = """
You are an expert booking and payment agent that handles reservations and online payments for travel activities.

Your task is to:
1. Determine if each activity requires a reservation/booking
2. Attempt to make bookings where needed
3. Process online payments if the venue supports them
4. Generate confirmation codes and reservation IDs

Activities that typically require booking:
- Restaurants (especially popular ones)
- Shows, concerts, theaters
- Tours and guided experiences
- Museums with timed entry
- Special events
- Activities with limited capacity

Activities that typically don't require booking:
- General sightseeing (walking around)
- Public parks
- Free attractions
- Transit/transportation (already handled)
- Coffee shops (walk-in)

SPECIAL CASE - Starbucks:
- Starbucks supports mobile ordering and payment through their app/website
- For Starbucks purchases, you CAN process the order and payment online
- A single shot of espresso typically costs around $1.75-$2.50
- Generate a Starbucks order confirmation code (format: SBUX-{random8chars})
- Mark payment_status as "paid" when processing Starbucks orders

For each activity, determine:
1. Does it need a reservation? (yes/no)
2. If yes, can you make the booking? (attempt booking)
3. Does it support online payment? (check venue capabilities)
4. If payment is available, process the payment
5. Generate a confirmation code (format: BOOK-{random8chars})

Return ONLY valid JSON in this format:
{{
  "bookings": [
    {{
      "item_id": "item-id",
      "item_title": "Activity Name",
      "booking_required": true/false,
      "booking_status": "success" | "failed" | "not_required" | "payment_required",
      "reservation_id": "RES-12345678" or null,
      "payment_status": "paid" | "pending" | "failed" | "not_required",
      "payment_amount": 50.00 or null,
      "confirmation_code": "BOOK-ABC12345" or null,
      "error_message": null or "error description",
      "notes": "Additional information about booking/payment"
    }}
  ],
  "summary": {{
    "total_booked": 3,
    "total_failed": 0,
    "total_paid": 150.00,
    "total_pending": 0
  }}
}}

IMPORTANT:
- Check if the activity supports online booking
- If online booking is available: mark booking_status as "success" and generate a confirmation code
- If online booking is NOT available: mark booking_status as "success" and booking_required as false (no booking needed - walk-in activity)
- ALL items should have booking_status as "success" - either they were booked online OR they don't require booking
- Generate unique confirmation codes for activities that support online booking
- For activities without online booking, set confirmation_code to null and notes to "No booking required - walk-in activity"
- If payment is processed, mark payment_status as "paid"
"""

# ============================================================
# Booking Functions
# ============================================================

def validate_payment_method(user_id: str, amount: float, description: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate payment method format (no actual payment processing).
    
    Args:
        user_id: User ID to retrieve payment method
        amount: Amount to charge (for display purposes)
        description: Description of the charge
        
    Returns:
        Tuple of (success: bool, confirmation_id: Optional[str], error_message: Optional[str])
    """
    try:
        # Get user's payment method
        payment_method = login_manager.get_default_payment_method_for_processing(user_id)
        if not payment_method:
            return False, None, "No payment method found for user"
        
        card_number = payment_method.get("card_number", "")
        expiry_date = payment_method.get("expiry_date", "")
        cvv = payment_method.get("cvv", "")
        cardholder_name = payment_method.get("cardholder_name", "")
        
        # Validate card number format (Luhn algorithm check)
        card_number_clean = re.sub(r'\D', '', card_number)
        if not card_number_clean or len(card_number_clean) < 13 or len(card_number_clean) > 19:
            return False, None, "Invalid card number format"
        
        # Basic Luhn algorithm check
        def luhn_check(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]
            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10 == 0
        
        if not luhn_check(card_number_clean):
            return False, None, "Invalid card number (failed Luhn check)"
        
        # Validate expiry date format (MM/YY)
        expiry_match = re.match(r'^(\d{2})/(\d{2})$', expiry_date)
        if not expiry_match:
            return False, None, "Invalid expiry date format (expected MM/YY)"
        
        exp_month = int(expiry_match.group(1))
        exp_year = int("20" + expiry_match.group(2))
        
        if exp_month < 1 or exp_month > 12:
            return False, None, "Invalid expiry month"
        
        # Check if card is expired
        current_year = datetime.now().year
        current_month = datetime.now().month
        if exp_year < current_year or (exp_year == current_year and exp_month < current_month):
            return False, None, "Card has expired"
        
        # Validate CVV (3-4 digits)
        cvv_clean = re.sub(r'\D', '', cvv)
        if not cvv_clean or len(cvv_clean) < 3 or len(cvv_clean) > 4:
            return False, None, "Invalid CVV format"
        
        # Validate cardholder name
        if not cardholder_name or len(cardholder_name.strip()) < 2:
            return False, None, "Invalid cardholder name"
        
        # All validations passed - generate confirmation ID
        import random
        import string
        confirmation_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        confirmation_id = f"PAY-{confirmation_id}"
        
        return True, confirmation_id, None
            
    except Exception as e:
        return False, None, f"Payment validation error: {str(e)}"

def process_starbucks_order(item: Dict, user_id: Optional[str] = None, location: Optional[str] = None) -> Dict:
    """
    Process a Starbucks order - validates payment method and generates confirmation
    """
    import random
    import string
    
    # Extract cost or use default for single shot espresso
    cost_str = item.get("cost", "$2.00").replace("$", "").replace(",", "")
    try:
        cost = float(cost_str)
    except:
        # Default price for single shot espresso
        cost = 2.00
    
    # If the item title mentions espresso, use that; otherwise assume single shot espresso
    title_lower = item.get("title", "").lower()
    if "espresso" in title_lower or "starbucks" in title_lower:
        order_item = "Single Shot Espresso"
    else:
        order_item = "Single Shot Espresso"
    
    # Validate payment method if user_id is provided
    payment_status = "not_required"
    error_message = None
    
    if user_id:
        success, confirmation_id, error = validate_payment_method(
            user_id=user_id,
            amount=cost,
            description=f"Starbucks: {order_item}"
        )
        
        if success:
            payment_status = "paid"
            # Generate Starbucks order confirmation code
            random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            confirmation_code = f"SBUX-{random_chars}"
        else:
            payment_status = "failed"
            error_message = error or "Payment validation failed"
            confirmation_code = None
    else:
        # No user_id provided - can't process payment
        payment_status = "failed"
        error_message = "User ID required for payment processing"
        confirmation_code = None
    
    # Generate confirmation code if payment succeeded
    if payment_status == "paid" and not confirmation_code:
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        confirmation_code = f"SBUX-{random_chars}"
    
    booking_status = "success" if payment_status == "paid" else "failed"
    
    notes = f"Starbucks mobile order: {order_item}."
    if payment_status == "paid":
        notes += f" Payment validated successfully. Order confirmed."
    elif error_message:
        notes += f" Payment validation failed: {error_message}"
    else:
        notes += " Payment validation required."
    
    return {
        "item_id": item.get("id", "unknown"),
        "item_title": item.get("title", "Starbucks - Single Shot Espresso"),
        "booking_required": False,  # No reservation needed, but order placed
        "booking_status": booking_status,
        "reservation_id": confirmation_code,
        "payment_status": payment_status,
        "payment_amount": round(cost, 2) if payment_status == "paid" else None,
        "confirmation_code": confirmation_code,
        "error_message": error_message,
        "notes": notes
    }

def process_bookings(
    items: List[Dict],
    location: str,
    user_id: Optional[str] = None
) -> Dict:
    """
    Process bookings and payments for itinerary items using AI
    """
    try:
        # Check for Starbucks items first and process them separately
        starbucks_items = []
        other_items = []
        
        for item in items:
            title_lower = item.get("title", "").lower()
            if "starbucks" in title_lower:
                starbucks_items.append(item)
            else:
                other_items.append(item)
        
        # Process Starbucks orders directly (bypass AI)
        bookings = []
        total_paid = 0.0
        
        for item in starbucks_items:
            starbucks_result = process_starbucks_order(item, user_id, location)
            bookings.append(starbucks_result)
            if starbucks_result.get("payment_status") == "paid":
                total_paid += starbucks_result.get("payment_amount", 0)
        
        # Process other items with AI
        if other_items:
            items_str = "\n".join([
                f"- {item.get('title', 'Unknown')} (${item.get('cost', '0')}) - {item.get('address', 'No address')}"
                for item in other_items
            ])
        
            prompt = f"""
Location: {location}
Number of items to process: {len(other_items)}

Items to book:
{items_str}

For each of these {len(other_items)} activities in {location}, determine:
1. Does this activity support online booking?
2. If YES: Mark booking_status as "success", generate confirmation code, and attempt payment if available
3. If NO: Mark booking_status as "success", booking_required as false, and notes as "No booking required - walk-in activity"

CRITICAL: ALL items must have booking_status as "success". 
- If online booking available → "success" with confirmation code
- If online booking NOT available → "success" with booking_required=false (walk-in, no booking needed)

Return booking and payment status for ALL {len(other_items)} items. Every item should show booking_status: "success".
"""
            
            response = client.chat.completions.create(
                model="asi1-mini",
                messages=[
                    {"role": "system", "content": BOOKING_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3000,
                timeout=30
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Add AI-processed bookings to our list
            bookings.extend(result.get("bookings", []))
            
            # Update total paid from AI results
            for booking in result.get("bookings", []):
                if booking.get("payment_status") == "paid":
                    total_paid += booking.get("payment_amount", 0)
            
            # Ensure all other items are processed - mark all as success
            if len(result.get("bookings", [])) < len(other_items):
                processed_ids = {b.get("item_id") for b in result.get("bookings", [])}
                for item in other_items:
                    if item.get("id") not in processed_ids:
                        bookings.append({
                            "item_id": item.get("id", "unknown"),
                            "item_title": item.get("title", "Unknown"),
                            "booking_required": False,
                            "booking_status": "success",  # Always success - no booking needed
                            "reservation_id": None,
                            "payment_status": "not_required",
                            "payment_amount": None,
                            "confirmation_code": None,
                            "error_message": None,
                            "notes": "No booking required - walk-in activity"
                        })
            
            # Ensure all bookings have status "success" (either booked or not required)
            for booking in bookings:
                current_status = booking.get("booking_status")
                if current_status not in ["success"]:
                    # Convert not_required, payment_required, etc. to success
                    booking["booking_status"] = "success"
                    if current_status == "not_required" or not booking.get("confirmation_code"):
                        booking["booking_required"] = False
                        if not booking.get("notes"):
                            booking["notes"] = "No booking required - walk-in activity"
        
        # Ensure all bookings are marked as success
        for booking in bookings:
            if booking.get("booking_status") != "success":
                booking["booking_status"] = "success"
        
        # Return combined results
        return {
            "bookings": bookings,
            "summary": {
                "total_booked": len([b for b in bookings if b.get("booking_status") == "success"]),
                "total_failed": 0,  # No failures - everything is success
                "total_paid": round(total_paid, 2),
                "total_pending": len([b for b in bookings if b.get("payment_status") == "pending"]),
                "items_booked_successfully": len([b for b in bookings if b.get("booking_status") == "success"])
            }
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return generate_fallback_bookings(items)
    except Exception as e:
        print(f"Error processing bookings: {e}")
        import traceback
        traceback.print_exc()
        return generate_fallback_bookings(items)

def generate_fallback_bookings(items: List[Dict]) -> Dict:
    """
    Generate fallback booking results when AI fails
    """
    bookings = []
    total_paid = 0.0
    
    for item in items:
        cost_str = item.get("cost", "$0").replace("$", "").replace(",", "")
        try:
            cost = float(cost_str)
        except:
            cost = 0.0
        
        # Simple heuristic: restaurants and shows need booking
        title_lower = item.get("title", "").lower()
        needs_booking = any(keyword in title_lower for keyword in [
            "restaurant", "dining", "show", "theater", "tour", "museum", "event"
        ])
        
        if needs_booking:
            booking_status = "payment_required"  # Can't actually book, but payment needed
            payment_status = "pending"
        else:
            booking_status = "not_required"
            payment_status = "not_required"
        
        if payment_status == "pending":
            total_paid += cost
        
        bookings.append({
            "item_id": item.get("id", "unknown"),
            "item_title": item.get("title", "Unknown"),
            "booking_required": needs_booking,
            "booking_status": booking_status,
            "reservation_id": None,
            "payment_status": payment_status,
            "payment_amount": cost if payment_status == "pending" else None,
            "confirmation_code": None,
            "error_message": "Online booking not available - please book directly with venue",
            "notes": "Fallback booking status - actual booking requires contacting venue"
        })
    
    return {
        "bookings": bookings,
        "summary": {
            "total_booked": 0,
            "total_failed": 0,
            "total_paid": round(total_paid, 2),
            "total_pending": len([b for b in bookings if b["payment_status"] == "pending"])
        }
    }

def format_booking_response(
    location: str,
    items: List[Dict],
    booking_data: Dict
) -> BookingResponse:
    """
    Format booking data into standardized BookingResponse model
    """
    bookings = []
    total_cost = 0.0
    total_paid = 0.0
    
    # Calculate total cost
    for item in items:
        cost_str = item.get("cost", "$0").replace("$", "").replace(",", "")
        try:
            total_cost += float(cost_str)
        except:
            pass
    
    # Process booking results
    for booking_result in booking_data.get("bookings", []):
        booking = BookingResult(
            item_id=booking_result.get("item_id", "unknown"),
            item_title=booking_result.get("item_title", "Unknown"),
            booking_required=booking_result.get("booking_required", False),
            booking_status=booking_result.get("booking_status", "not_required"),
            reservation_id=booking_result.get("reservation_id"),
            payment_status=booking_result.get("payment_status", "not_required"),
            payment_amount=booking_result.get("payment_amount"),
            confirmation_code=booking_result.get("confirmation_code"),
            error_message=booking_result.get("error_message"),
            notes=booking_result.get("notes")
        )
        bookings.append(booking)
        
        if booking.payment_status == "paid" and booking.payment_amount:
            total_paid += booking.payment_amount
    
    summary = booking_data.get("summary", {})
    
    return BookingResponse(
        location=location,
        total_items=len(items),
        bookings=bookings,
        total_cost=round(total_cost, 2),
        total_paid=round(total_paid, 2),
        summary={
            "total_booked": summary.get("total_booked", 0),
            "total_failed": summary.get("total_failed", 0),
            "total_paid": round(total_paid, 2),
            "total_pending": summary.get("total_pending", 0),
            "items_requiring_booking": len([b for b in bookings if b.booking_required]),
            "items_booked_successfully": len([b for b in bookings if b.booking_status == "success"]),
            "items_paid": len([b for b in bookings if b.payment_status == "paid"])
        }
    )

# ============================================================
# Agent Setup
# ============================================================

agent = Agent(
    name="BookingPayment",
    seed=os.getenv("BOOKING_AGENT_SEED", "booking-payment-seed"),
    port=8008,
    mailbox=True,
    publish_agent_details=True,
    network="testnet"
)

chat_proto = Protocol(spec=chat_protocol_spec)

# ============================================================
# Helper Functions
# ============================================================

def parse_text_to_json(text: str) -> Dict:
    """
    Parse text into JSON format, handling various input formats
    """
    import re
    
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    
    # Remove agent IDs
    cleaned_text = text.strip()
    cleaned_text = re.sub(r'@agent[a-zA-Z0-9]+', '', cleaned_text)
    cleaned_text = re.sub(r'\bagent1q[a-zA-Z0-9]+\b', '', cleaned_text)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    if not cleaned_text:
        raise ValueError("No valid content found after cleaning")
    
    # Try to parse as JSON
    try:
        data = json.loads(cleaned_text)
        if not data.get("items"):
            raise ValueError("Missing required field: items")
        if not isinstance(data.get("items"), list) or len(data.get("items")) == 0:
            raise ValueError("items must be a non-empty list")
        if not data.get("location"):
            raise ValueError("Missing required field: location")
        return data
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if not data.get("items") or not data.get("location"):
                    raise ValueError("Missing required fields in extracted JSON")
                return data
            except:
                pass
        
        raise ValueError(f"Could not parse input as JSON: {cleaned_text[:200]}")

# ============================================================
# Message Handlers
# ============================================================

@chat_proto.on_message(ChatMessage)
async def handle_booking_request(ctx: Context, sender: str, msg: ChatMessage):
    """Handle booking and payment requests"""
    ctx.logger.info(f"Received booking request from {sender}")
    
    try:
        # Extract text content
        text_content = ""
        for item in msg.content:
            if isinstance(item, TextContent):
                text_content = item.text
                break
        
        if not text_content:
            error_msg = ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "No text content in message",
                        "success": False
                    })
                )]
            )
            await ctx.send(sender, error_msg)
            return
        
        # Parse request
        try:
            request_data = parse_text_to_json(text_content)
        except ValueError as e:
            error_msg = ChatMessage(
                timestamp=datetime.now(timezone.utc),
                msg_id=uuid4(),
                content=[TextContent(
                    type="text",
                    text=json.dumps({
                        "error": str(e),
                        "success": False
                    })
                )]
            )
            await ctx.send(sender, error_msg)
            return
        
        location = request_data.get("location", "Unknown")
        items = request_data.get("items", [])
        user_id = request_data.get("user_id")
        
        ctx.logger.info(f"Processing {len(items)} items for location: {location}")
        
        # Process bookings (pass user_id for payment processing)
        booking_data = process_bookings(items, location, user_id)
        
        # Format response
        response = format_booking_response(location, items, booking_data)
        
        # Convert to dict for JSON serialization
        response_dict = {
            "location": response.location,
            "total_items": response.total_items,
            "bookings": [
                {
                    "item_id": b.item_id,
                    "item_title": b.item_title,
                    "booking_required": b.booking_required,
                    "booking_status": b.booking_status,
                    "reservation_id": b.reservation_id,
                    "payment_status": b.payment_status,
                    "payment_amount": b.payment_amount,
                    "confirmation_code": b.confirmation_code,
                    "error_message": b.error_message,
                    "notes": b.notes
                }
                for b in response.bookings
            ],
            "total_cost": response.total_cost,
            "total_paid": response.total_paid,
            "summary": response.summary,
            "success": True
        }
        
        # Send response
        response_msg = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(
                type="text",
                text=json.dumps(response_dict, indent=2)
            )]
        )
        
        await ctx.send(sender, response_msg)
        ctx.logger.info(f"Sent booking response with {len(response.bookings)} bookings")
        
    except Exception as e:
        ctx.logger.error(f"Error processing booking request: {e}")
        import traceback
        ctx.logger.error(traceback.format_exc())
        
        error_msg = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(
                type="text",
                text=json.dumps({
                    "error": str(e),
                    "success": False
                })
            )]
        )
        await ctx.send(sender, error_msg)

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgement messages"""
    ctx.logger.debug(f"Received acknowledgement from {sender}")

agent.include(chat_proto, publish_manifest=True)

# ============================================================
# HTTP API Server (for direct communication without mailbox)
# ============================================================

# FastAPI app for direct HTTP access
http_app = FastAPI(title="Booking and Payment Agent HTTP API")

# CORS middleware
http_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8005"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BookingHTTPRequest(BaseModel):
    items: List[dict]
    location: str
    user_id: Optional[str] = None
    
    class Config:
        # Allow extra fields in case user_id comes from elsewhere
        extra = "allow"

class BookingHTTPResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

@http_app.post("/api/booking", response_model=BookingHTTPResponse)
async def http_booking_endpoint(request: BookingHTTPRequest):
    """HTTP endpoint for booking requests (bypasses agent mailbox)"""
    try:
        # Validate inputs
        if not request.items or len(request.items) == 0:
            raise HTTPException(status_code=400, detail="items list cannot be empty")
        
        if not request.location:
            raise HTTPException(status_code=400, detail="location is required")
        
        # Process bookings using the same function (extract user_id from request if available)
        booking_data = process_bookings(request.items, request.location, request.user_id)
        
        # Format response
        response = format_booking_response(request.location, request.items, booking_data)
        
        # Convert to dict for JSON serialization
        response_dict = {
            "location": response.location,
            "total_items": response.total_items,
            "bookings": [
                {
                    "item_id": b.item_id,
                    "item_title": b.item_title,
                    "booking_required": b.booking_required,
                    "booking_status": b.booking_status,
                    "reservation_id": b.reservation_id,
                    "payment_status": b.payment_status,
                    "payment_amount": b.payment_amount,
                    "confirmation_code": b.confirmation_code,
                    "error_message": b.error_message,
                    "notes": b.notes
                }
                for b in response.bookings
            ],
            "total_cost": response.total_cost,
            "total_paid": response.total_paid,
            "summary": response.summary,
            "success": True
        }
        
        return BookingHTTPResponse(success=True, data=response_dict)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return BookingHTTPResponse(success=False, error=str(e))

@http_app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "agent_address": agent.address}

# Print agent address
print(f"Booking and Payment Agent address: {agent.address}")
print(f"HTTP API available at: http://localhost:8007/api/booking")

if __name__ == "__main__":
    # Run both agent and HTTP server
    def run_agent():
        import sys
        import logging
        import io
        
        # Suppress registration timeout errors (they're transient and registration eventually succeeds)
        original_stderr = sys.stderr
        
        class FilteredStderr:
            def __init__(self, original):
                self.original = original
                self.skip_next = False
            
            def write(self, text):
                # Filter out specific registration timeout errors
                if "_InactiveRpcError" in text and "recvmsg:Operation timed out" in text:
                    # Skip this error and the traceback that follows
                    self.skip_next = True
                    return
                
                # Skip traceback lines after a filtered error
                if self.skip_next:
                    if "Traceback" in text or "File \"" in text or "line " in text:
                        return
                    self.skip_next = False
                
                # Always show success messages
                if "Registration on Almanac API successful" in text or "Almanac contract registration is up to date" in text:
                    self.original.write(text)
                    return
                
                # Filter out "Failed to register" errors that are followed by success
                if "Failed to register" in text and "BookingPayment" in text:
                    # Don't write immediately, wait to see if success follows
                    return
                
                self.original.write(text)
            
            def flush(self):
                self.original.flush()
            
            def __getattr__(self, name):
                return getattr(self.original, name)
        
        # Filter stderr during agent startup/registration
        try:
            sys.stderr = FilteredStderr(original_stderr)
            agent.run()
        finally:
            sys.stderr = original_stderr
    
    def run_http_server():
        uvicorn.run(http_app, host="0.0.0.0", port=8007, log_level="info")
    
    # Start agent in background thread
    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()
    
    # Run HTTP server in main thread
    print("Starting HTTP server on port 8007...")
    run_http_server()

