#!/usr/bin/env python3
"""
Authentication API Server for Hack-Brown
Provides REST API endpoints for user authentication, registration, and onboarding
"""
import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from dotenv import load_dotenv

from Login import LoginManager

load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Hack-Brown Auth API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize LoginManager
login_manager = LoginManager()

# Request/Response Models
class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: Optional[bool] = False

class GoogleSignInRequest(BaseModel):
    id_token: str
    remember_me: Optional[bool] = False

class OnboardingRequest(BaseModel):
    favorite_activities: list[str]
    favorite_stores: list[str]

class UpdatePreferencesRequest(BaseModel):
    favorite_activities: Optional[list[str]] = None
    favorite_stores: Optional[list[str]] = None
    budget_range: Optional[dict] = None

# API Endpoints
@app.post("/auth/register")
async def register(request: RegisterRequest):
    """Register a new user"""
    try:
        success, message = login_manager.register_user(
            email=request.email,
            username=request.username,
            password=request.password,
            full_name=request.full_name
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        # After registration, automatically log in the user
        login_success, login_msg, token = login_manager.login_user(
            username_or_email=request.email,
            password=request.password,
            remember_me=False
        )
        
        if not login_success:
            return {
                "success": True,
                "message": message,
                "token": None,
                "onboarding_required": True
            }
        
        # Check if user needs onboarding
        try:
            is_valid, user_data = login_manager.verify_session(token)
            if not is_valid or not user_data:
                # Session verification failed, but registration succeeded
                return {
                    "success": True,
                    "message": message,
                    "token": token,
                    "onboarding_required": True
                }
            
            user_profile = login_manager.get_user_profile(user_data["user_id"])
            onboarding_required = not user_profile.get("onboarding_completed", False) if user_profile else True
        except Exception as profile_error:
            # If profile check fails, assume onboarding is required
            print(f"Warning: Could not check onboarding status: {profile_error}")
            onboarding_required = True
        
        return {
            "success": True,
            "message": message,
            "token": token,
            "onboarding_required": onboarding_required
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Registration error: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/auth/login")
async def login(request: LoginRequest):
    """Login user with email and password"""
    try:
        success, message, token = login_manager.login_user(
            username_or_email=request.email,
            password=request.password,
            remember_me=request.remember_me or False
        )
        
        if not success:
            raise HTTPException(status_code=401, detail=message)
        
        # Check if user needs onboarding
        user_profile = login_manager.get_user_profile(
            login_manager.verify_session(token)[1]["user_id"]
        )
        onboarding_required = not user_profile.get("onboarding_completed", False) if user_profile else True
        
        return {
            "success": True,
            "message": message,
            "token": token,
            "onboarding_required": onboarding_required
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/auth/google")
async def google_sign_in(request: GoogleSignInRequest):
    """Sign in with Google OAuth2 token"""
    try:
        success, message, token = login_manager.google_sign_in(
            google_token=request.id_token,
            remember_me=request.remember_me or False
        )
        
        if not success:
            raise HTTPException(status_code=401, detail=message)
        
        # Check if user needs onboarding
        user_profile = login_manager.get_user_profile(
            login_manager.verify_session(token)[1]["user_id"]
        )
        onboarding_required = not user_profile.get("onboarding_completed", False) if user_profile else True
        
        return {
            "success": True,
            "message": message,
            "token": token,
            "onboarding_required": onboarding_required
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google sign-in failed: {str(e)}")

@app.get("/auth/verify")
async def verify_session(authorization: Optional[str] = Header(None)):
    """Verify session token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    is_valid, user_data = login_manager.verify_session(token)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Get full user profile
    user_profile = login_manager.get_user_profile(user_data["user_id"])
    if not user_profile:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "success": True,
        "user": user_profile,
        "onboarding_required": not user_profile.get("onboarding_completed", False)
    }

@app.post("/auth/onboarding")
async def complete_onboarding(
    request: OnboardingRequest,
    authorization: Optional[str] = Header(None)
):
    """Complete user onboarding with preferences"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    is_valid, user_data = login_manager.verify_session(token)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        # Update user preferences with onboarding data
        preferences = {
            "activity_categories": request.favorite_activities,
            "favorite_stores": request.favorite_stores,
            "onboarding_completed": True
        }
        
        success, message = login_manager.update_user_preferences(
            user_data["user_id"],
            preferences
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "success": True,
            "message": "Onboarding completed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Onboarding failed: {str(e)}")

@app.put("/auth/preferences")
async def update_preferences(
    request: UpdatePreferencesRequest,
    authorization: Optional[str] = Header(None)
):
    """Update user preferences"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    is_valid, user_data = login_manager.verify_session(token)
    
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    try:
        # Get current preferences
        user_profile = login_manager.get_user_profile(user_data["user_id"])
        current_prefs = user_profile.get("preferences", {}) if user_profile else {}
        
        # Update preferences
        updated_prefs = current_prefs.copy()
        if request.favorite_activities is not None:
            updated_prefs["activity_categories"] = request.favorite_activities
        if request.favorite_stores is not None:
            updated_prefs["favorite_stores"] = request.favorite_stores
        if request.budget_range is not None:
            updated_prefs["budget_range"] = request.budget_range
        
        success, message = login_manager.update_user_preferences(
            user_data["user_id"],
            updated_prefs
        )
        
        if not success:
            raise HTTPException(status_code=400, detail=message)
        
        return {
            "success": True,
            "message": "Preferences updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update preferences failed: {str(e)}")

@app.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    success = login_manager.logout_user(token)
    
    if not success:
        raise HTTPException(status_code=400, detail="Logout failed")
    
    return {"success": True, "message": "Logged out successfully"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "auth-api"}

if __name__ == "__main__":
    port = int(os.getenv("AUTH_SERVER_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

