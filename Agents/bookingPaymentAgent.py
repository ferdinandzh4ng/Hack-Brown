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
from typing import Optional, List, Dict, Any
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

load_dotenv()

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
- Be realistic about what can be booked online vs. what requires phone calls
- Only mark as "success" if you can actually make the booking
- For activities that don't support online booking, mark as "not_required" or "payment_required" (if payment can be made at venue)
- Generate unique confirmation codes for successful bookings
- If payment is processed, mark payment_status as "paid"
"""

# ============================================================
# Booking Functions
# ============================================================

def process_bookings(
    items: List[Dict],
    location: str
) -> Dict:
    """
    Process bookings and payments for itinerary items using AI
    """
    try:
        items_str = "\n".join([
            f"- {item.get('title', 'Unknown')} (${item.get('cost', '0')}) - {item.get('address', 'No address')}"
            for item in items
        ])
        
        prompt = f"""
Location: {location}
Number of items to process: {len(items)}

Items to book:
{items_str}

For each of these {len(items)} activities in {location}, determine:
1. Does this activity require a reservation/booking?
2. Can you make the booking online?
3. Does the venue support online payment?
4. If yes to both, make the booking and process payment
5. Generate confirmation codes for successful bookings

Be realistic - only mark bookings as successful if the venue actually supports online booking.
For walk-in activities (like coffee shops, parks), mark as "not_required".
For activities that need booking but don't support online booking, mark as "payment_required" (user can pay at venue).

Return booking and payment status for ALL {len(items)} items.
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
        
        # Ensure all items are processed
        if len(result.get("bookings", [])) < len(items):
            # Fill in missing items
            processed_ids = {b.get("item_id") for b in result.get("bookings", [])}
            for item in items:
                if item.get("id") not in processed_ids:
                    result["bookings"].append({
                        "item_id": item.get("id", "unknown"),
                        "item_title": item.get("title", "Unknown"),
                        "booking_required": False,
                        "booking_status": "not_required",
                        "reservation_id": None,
                        "payment_status": "not_required",
                        "payment_amount": None,
                        "confirmation_code": None,
                        "error_message": None,
                        "notes": "No booking required for this activity"
                    })
        
        return result
        
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
        
        # Process bookings
        booking_data = process_bookings(items, location)
        
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
        
        # Process bookings using the same function
        booking_data = process_bookings(request.items, request.location)
        
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
        agent.run()
    
    def run_http_server():
        uvicorn.run(http_app, host="0.0.0.0", port=8007, log_level="info")
    
    # Start agent in background thread
    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()
    
    # Run HTTP server in main thread
    print("Starting HTTP server on port 8007...")
    run_http_server()

