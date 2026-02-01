# Booking Implementation Plan
## One-Click Booking & Payment System

### Overview
This document outlines the architecture and implementation plan for a compliant, secure one-click booking system that uses official APIs and follows payment industry best practices.

---

## 🎯 Core Principles

1. **Use Official APIs Only** - No scraping, no form automation
2. **Store Payment Tokens, Not Cards** - PCI DSS compliance
3. **User Consent Required** - Explicit authorization for each booking
4. **Secure Payment Processing** - Stripe or similar certified processor
5. **Transparent Flow** - User sees what they're booking before confirmation

---

## 📋 Architecture Overview

```
User Request → Schedule Generation → User Selects Items → 
One-Click Booking → API Integration → Payment Processing → Confirmation
```

### Components

1. **Frontend Booking UI** - Selection and confirmation interface
2. **Booking Agent** - Orchestrates booking flow
3. **Payment Service** - Stripe integration for secure payments
4. **API Integrations** - Official partner APIs (OpenTable, Eventbrite, etc.)
5. **Database** - Store booking confirmations and payment tokens

---

## 🔧 Implementation Plan

### Phase 1: Payment Infrastructure Setup

#### 1.1 Stripe Integration
**Goal**: Set up secure payment token storage and processing

**Tasks**:
- [ ] Install Stripe Python SDK: `pip install stripe`
- [ ] Create Stripe account and get API keys
- [ ] Set up Stripe webhook endpoint for payment confirmations
- [ ] Create payment method storage schema

**Code Structure**:
```python
# payment_service.py
import stripe
from typing import Optional, Dict

class PaymentService:
    def __init__(self):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    def create_customer(self, user_id: str, email: str) -> str:
        """Create Stripe customer and return customer_id"""
        customer = stripe.Customer.create(
            email=email,
            metadata={"user_id": user_id}
        )
        return customer.id
    
    def save_payment_method(self, customer_id: str, payment_method_id: str):
        """Attach payment method to customer"""
        stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer_id
        )
        # Set as default
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": payment_method_id}
        )
    
    def create_payment_intent(
        self, 
        customer_id: str, 
        amount: float, 
        currency: str = "usd"
    ) -> Dict:
        """Create payment intent for booking"""
        return stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency=currency,
            customer=customer_id,
            payment_method_types=["card"],
            confirmation_method="manual",
            confirm=False
        )
    
    def confirm_payment(self, payment_intent_id: str) -> Dict:
        """Confirm and process payment"""
        return stripe.PaymentIntent.confirm(payment_intent_id)
```

**Database Schema** (add to Login.py or separate payment table):
```python
# Payment method storage
{
    "user_id": "user123",
    "stripe_customer_id": "cus_abc123",
    "payment_methods": [
        {
            "id": "pm_xyz789",
            "type": "card",
            "last4": "4242",
            "brand": "visa",
            "is_default": True
        }
    ],
    "created_at": "2026-01-15T10:00:00Z"
}
```

#### 1.2 Payment Method Setup Flow
**Frontend Flow**:
1. User clicks "Add Payment Method"
2. Frontend calls Stripe.js to create payment method
3. Send payment method ID to backend
4. Backend saves to Stripe customer
5. Store customer_id in user profile

**Backend Endpoint**:
```python
@app.post("/api/payment/setup")
async def setup_payment_method(
    user_id: str,
    payment_method_id: str
):
    """Save payment method for user"""
    # Get or create Stripe customer
    user_profile = login_manager.get_user_profile(user_id)
    if not user_profile.get("stripe_customer_id"):
        customer = payment_service.create_customer(user_id, user_profile["email"])
        login_manager.update_user_profile(user_id, {"stripe_customer_id": customer})
    
    # Attach payment method
    payment_service.save_payment_method(
        user_profile["stripe_customer_id"],
        payment_method_id
    )
    
    return {"success": True, "customer_id": customer}
```

---

### Phase 2: Booking API Integrations

#### 2.1 Restaurant Bookings - OpenTable API
**Goal**: Integrate with OpenTable for restaurant reservations

**Setup**:
- [ ] Apply for OpenTable Partner API access
- [ ] Get API credentials
- [ ] Install OpenTable SDK or use REST API

**Implementation**:
```python
# booking_services/opentable_service.py
import requests
from typing import Optional, Dict, List

class OpenTableService:
    def __init__(self):
        self.api_key = os.getenv("OPENTABLE_API_KEY")
        self.base_url = "https://api.opentable.com/v1"
    
    def search_restaurants(
        self, 
        location: str, 
        cuisine: Optional[str] = None
    ) -> List[Dict]:
        """Search for restaurants"""
        params = {
            "location": location,
            "api_key": self.api_key
        }
        if cuisine:
            params["cuisine"] = cuisine
        
        response = requests.get(
            f"{self.base_url}/restaurants",
            params=params
        )
        return response.json().get("restaurants", [])
    
    def check_availability(
        self, 
        restaurant_id: str, 
        date: str, 
        time: str, 
        party_size: int
    ) -> Dict:
        """Check table availability"""
        response = requests.get(
            f"{self.base_url}/restaurants/{restaurant_id}/availability",
            params={
                "date": date,
                "time": time,
                "party_size": party_size,
                "api_key": self.api_key
            }
        )
        return response.json()
    
    def create_reservation(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
        customer_info: Dict
    ) -> Dict:
        """Create reservation via OpenTable API"""
        response = requests.post(
            f"{self.base_url}/reservations",
            json={
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
                "customer": customer_info,
                "api_key": self.api_key
            }
        )
        return response.json()
```

**Alternative**: If OpenTable API access is restricted, use:
- **SevenRooms API** (restaurant reservations)
- **Resy API** (limited access, requires partnership)

#### 2.2 Event Tickets - Eventbrite API
**Goal**: Integrate with Eventbrite for event ticket purchases

**Setup**:
- [ ] Create Eventbrite developer account
- [ ] Get OAuth credentials
- [ ] Set up OAuth flow for API access

**Implementation**:
```python
# booking_services/eventbrite_service.py
import requests
from typing import Optional, Dict, List

class EventbriteService:
    def __init__(self):
        self.api_key = os.getenv("EVENTBRITE_API_KEY")
        self.base_url = "https://www.eventbriteapi.com/v3"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def search_events(
        self, 
        location: str, 
        query: Optional[str] = None
    ) -> List[Dict]:
        """Search for events"""
        params = {
            "location.address": location,
            "expand": "venue"
        }
        if query:
            params["q"] = query
        
        response = requests.get(
            f"{self.base_url}/events/search",
            params=params,
            headers=self.headers
        )
        return response.json().get("events", [])
    
    def get_event_details(self, event_id: str) -> Dict:
        """Get event details including ticket classes"""
        response = requests.get(
            f"{self.base_url}/events/{event_id}",
            params={"expand": "ticket_classes,venue"},
            headers=self.headers
        )
        return response.json()
    
    def create_order(
        self,
        event_id: str,
        ticket_class_id: str,
        quantity: int,
        customer_info: Dict
    ) -> Dict:
        """Create order for tickets"""
        # Step 1: Create order
        order_data = {
            "event_id": event_id,
            "ticket_class_id": ticket_class_id,
            "quantity": quantity,
            "costs": {
                "gross": {
                    "value": "USD",
                    "major_value": "50.00"
                }
            }
        }
        
        order_response = requests.post(
            f"{self.base_url}/orders",
            json=order_data,
            headers=self.headers
        )
        order = order_response.json()
        
        # Step 2: Confirm order (after payment)
        # This would be called after Stripe payment is confirmed
        return order
```

**Alternative APIs**:
- **Ticketmaster Discovery API** - Search only (no direct purchase)
- **Viator API** - Tours and attractions
- **StubHub API** - Secondary market (requires partnership)

#### 2.3 Generic Booking Handler
**Goal**: Unified interface for different booking types

**Implementation**:
```python
# booking_services/booking_orchestrator.py
from typing import Dict, List, Optional
from enum import Enum

class BookingType(Enum):
    RESTAURANT = "restaurant"
    EVENT = "event"
    TOUR = "tour"
    ATTRACTION = "attraction"

class BookingOrchestrator:
    def __init__(self):
        self.opentable = OpenTableService()
        self.eventbrite = EventbriteService()
    
    async def book_item(
        self,
        item: Dict,
        user_id: str,
        payment_intent_id: Optional[str] = None
    ) -> Dict:
        """Book a single item based on its type"""
        booking_type = self._detect_booking_type(item)
        
        if booking_type == BookingType.RESTAURANT:
            return await self._book_restaurant(item, user_id)
        elif booking_type == BookingType.EVENT:
            return await self._book_event(item, user_id, payment_intent_id)
        else:
            return {
                "success": False,
                "error": f"Booking type {booking_type} not yet supported"
            }
    
    def _detect_booking_type(self, item: Dict) -> BookingType:
        """Detect what type of booking this is"""
        category = item.get("category", "").lower()
        title = item.get("title", "").lower()
        
        if "restaurant" in category or "dining" in category:
            return BookingType.RESTAURANT
        elif "event" in category or "ticket" in category:
            return BookingType.EVENT
        elif "tour" in category:
            return BookingType.TOUR
        else:
            return BookingType.ATTRACTION
    
    async def _book_restaurant(self, item: Dict, user_id: str) -> Dict:
        """Book restaurant reservation"""
        # Extract restaurant info from item
        restaurant_id = item.get("venue_id")  # Would need to be stored during schedule generation
        date = item.get("start_time")[:10]  # Extract date
        time = item.get("start_time")[11:16]  # Extract time
        party_size = item.get("party_size", 2)
        
        # Get user info
        user_profile = login_manager.get_user_profile(user_id)
        customer_info = {
            "name": user_profile.get("name"),
            "email": user_profile.get("email"),
            "phone": user_profile.get("phone")
        }
        
        # Create reservation
        result = self.opentable.create_reservation(
            restaurant_id=restaurant_id,
            date=date,
            time=time,
            party_size=party_size,
            customer_info=customer_info
        )
        
        return {
            "success": True,
            "booking_id": result.get("reservation_id"),
            "confirmation_code": result.get("confirmation_code"),
            "type": "restaurant"
        }
    
    async def _book_event(
        self, 
        item: Dict, 
        user_id: str,
        payment_intent_id: str
    ) -> Dict:
        """Book event tickets (requires payment)"""
        event_id = item.get("event_id")
        ticket_class_id = item.get("ticket_class_id")
        quantity = item.get("quantity", 1)
        
        # Get user info
        user_profile = login_manager.get_user_profile(user_id)
        
        # Create order
        order = self.eventbrite.create_order(
            event_id=event_id,
            ticket_class_id=ticket_class_id,
            quantity=quantity,
            customer_info={
                "email": user_profile.get("email"),
                "name": user_profile.get("name")
            }
        )
        
        # Confirm order after payment
        if payment_intent_id:
            # Verify payment was successful
            payment_status = payment_service.get_payment_status(payment_intent_id)
            if payment_status == "succeeded":
                # Confirm Eventbrite order
                confirmed_order = self.eventbrite.confirm_order(order["id"])
                return {
                    "success": True,
                    "booking_id": confirmed_order["id"],
                    "confirmation_code": confirmed_order.get("confirmation_code"),
                    "tickets": confirmed_order.get("tickets"),
                    "type": "event"
                }
        
        return {
            "success": False,
            "error": "Payment required for event bookings"
        }
```

---

### Phase 3: One-Click Booking Flow

#### 3.1 Frontend Booking UI
**Components Needed**:
1. **Booking Selection** - User selects items to book
2. **Payment Method Selection** - Choose saved payment method
3. **Booking Confirmation** - Review before finalizing
4. **Booking Status** - Show progress and results

**Flow**:
```
User selects items → Review booking → Choose payment method → 
Confirm booking → Backend processes → Show confirmation
```

#### 3.2 Backend Booking Endpoint
**Implementation**:
```python
# In bookingPaymentAgent.py or bridge_server.py

@app.post("/api/booking/one-click")
async def one_click_booking(request: BookingRequest):
    """
    One-click booking flow:
    1. Validate items
    2. Check availability
    3. Create payment intent
    4. Book items
    5. Confirm payment
    6. Return confirmations
    """
    user_id = request.user_id
    items = request.items
    
    # Step 1: Validate user has payment method
    user_profile = login_manager.get_user_profile(user_id)
    if not user_profile.get("stripe_customer_id"):
        raise HTTPException(
            status_code=400,
            detail="No payment method on file. Please add a payment method first."
        )
    
    # Step 2: Calculate total cost
    total_cost = sum(float(item.get("cost", 0).replace("$", "")) for item in items)
    
    # Step 3: Create payment intent
    payment_intent = payment_service.create_payment_intent(
        customer_id=user_profile["stripe_customer_id"],
        amount=total_cost
    )
    
    # Step 4: Book each item
    booking_results = []
    booking_orchestrator = BookingOrchestrator()
    
    for item in items:
        try:
            # Check if item requires payment
            item_cost = float(item.get("cost", 0).replace("$", ""))
            requires_payment = item_cost > 0
            
            if requires_payment:
                # Book with payment
                result = await booking_orchestrator.book_item(
                    item=item,
                    user_id=user_id,
                    payment_intent_id=payment_intent["id"]
                )
            else:
                # Book without payment (free reservation)
                result = await booking_orchestrator.book_item(
                    item=item,
                    user_id=user_id
                )
            
            booking_results.append({
                "item_id": item.get("id"),
                "item_title": item.get("title"),
                "success": result.get("success", False),
                "booking_id": result.get("booking_id"),
                "confirmation_code": result.get("confirmation_code"),
                "error": result.get("error")
            })
        except Exception as e:
            booking_results.append({
                "item_id": item.get("id"),
                "item_title": item.get("title"),
                "success": False,
                "error": str(e)
            })
    
    # Step 5: Confirm payment if all bookings succeeded
    all_succeeded = all(r.get("success") for r in booking_results)
    if all_succeeded and total_cost > 0:
        payment_service.confirm_payment(payment_intent["id"])
    
    return {
        "success": all_succeeded,
        "payment_intent_id": payment_intent["id"],
        "bookings": booking_results,
        "total_cost": total_cost
    }
```

---

### Phase 4: User Consent & Authorization

#### 4.1 Booking Authorization Model
**Store user preferences**:
```python
# In user profile
{
    "booking_preferences": {
        "auto_book_enabled": False,  # Default: require confirmation
        "max_auto_spend": 50.00,  # Max amount for auto-booking
        "allowed_booking_types": ["restaurant", "event"],
        "require_confirmation_above": 100.00
    }
}
```

#### 4.2 Consent Flow
```python
async def check_booking_authorization(
    user_id: str,
    items: List[Dict],
    total_cost: float
) -> Dict:
    """Check if user has authorized this booking"""
    user_profile = login_manager.get_user_profile(user_id)
    prefs = user_profile.get("booking_preferences", {})
    
    # Always require confirmation for now
    if not prefs.get("auto_book_enabled", False):
        return {
            "authorized": False,
            "requires_confirmation": True,
            "message": "Please confirm this booking"
        }
    
    # Check max spend
    max_spend = prefs.get("max_auto_spend", 0)
    if total_cost > max_spend:
        return {
            "authorized": False,
            "requires_confirmation": True,
            "message": f"Booking exceeds auto-spend limit of ${max_spend}"
        }
    
    return {
        "authorized": True,
        "requires_confirmation": False
    }
```

---

### Phase 5: Error Handling & Rollback

#### 5.1 Transaction Safety
```python
async def safe_booking_transaction(
    items: List[Dict],
    user_id: str,
    payment_intent_id: str
) -> Dict:
    """Book items with rollback on failure"""
    bookings = []
    
    try:
        # Book all items
        for item in items:
            result = await booking_orchestrator.book_item(item, user_id, payment_intent_id)
            bookings.append(result)
            
            if not result.get("success"):
                # Rollback: cancel previous bookings
                await rollback_bookings(bookings)
                # Cancel payment intent
                payment_service.cancel_payment_intent(payment_intent_id)
                raise Exception(f"Failed to book {item.get('title')}")
        
        # All succeeded - confirm payment
        payment_service.confirm_payment(payment_intent_id)
        return {"success": True, "bookings": bookings}
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "bookings": bookings
        }

async def rollback_bookings(bookings: List[Dict]):
    """Cancel bookings if payment fails"""
    for booking in bookings:
        if booking.get("success") and booking.get("booking_id"):
            try:
                # Cancel booking via API
                booking_service.cancel_booking(booking["booking_id"])
            except:
                pass  # Log error but continue
```

---

## 📦 Required Dependencies

```bash
pip install stripe
pip install requests
pip install python-dotenv
# Add API-specific SDKs as needed:
# pip install eventbrite-python
# pip install opentable-python (if available)
```

## 🔐 Environment Variables

```env
# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# OpenTable (if available)
OPENTABLE_API_KEY=...

# Eventbrite
EVENTBRITE_API_KEY=...
EVENTBRITE_CLIENT_SECRET=...

# Database
DATABASE_URL=...
```

## 🚀 Implementation Order

1. **Week 1**: Stripe payment setup and payment method storage
2. **Week 2**: OpenTable API integration (or alternative)
3. **Week 3**: Eventbrite API integration
4. **Week 4**: One-click booking flow and UI
5. **Week 5**: Error handling, rollback, and testing

## ⚠️ Important Notes

1. **API Access**: Most booking APIs require partner/developer access. Apply early.
2. **Testing**: Use test/sandbox environments for all APIs during development.
3. **Webhooks**: Set up webhooks for payment confirmations and booking status updates.
4. **Compliance**: Ensure PCI DSS compliance when handling payment data.
5. **Rate Limits**: Be aware of API rate limits and implement proper queuing.

## 📝 Next Steps

1. Set up Stripe account and get API keys
2. Apply for OpenTable/Eventbrite API access
3. Create payment method storage in database
4. Implement payment service class
5. Build booking orchestrator
6. Create one-click booking endpoint
7. Add frontend booking UI
8. Test end-to-end flow

---

## Alternative: Simulated Booking (Development Phase)

If API access is not immediately available, create a simulated booking service:

```python
class SimulatedBookingService:
    """Simulated booking for development/testing"""
    
    async def book_item(self, item: Dict, user_id: str) -> Dict:
        # Simulate API delay
        await asyncio.sleep(1)
        
        # Return simulated confirmation
        return {
            "success": True,
            "booking_id": f"SIM_{uuid4().hex[:8]}",
            "confirmation_code": f"CONF-{random.randint(1000, 9999)}",
            "type": "simulated",
            "note": "This is a simulated booking for development"
        }
```

This allows frontend and flow development while waiting for API access.

