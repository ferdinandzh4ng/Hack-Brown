"""
Login system for Hack-Brown with MongoDB integration.
Handles user authentication, registration, session management, and Google OAuth2 sign-in.
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

load_dotenv()

# Google OAuth2 imports
try:
    from google.auth.transport import requests
    from google.oauth2 import id_token
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    print("Warning: google-auth library not installed. Google Sign-In will be disabled.")


class LoginManager:
    """Manages user authentication and MongoDB interactions"""
    
    def __init__(self):
        """Initialize MongoDB connection and collections"""
        self.client = self._connect_mongodb()
        if self.client:
            self.db = self.client[os.getenv("MONGODB_DATABASE", "HackBrown")]
            self._setup_collections()
        else:
            self.db = None
    
    def _connect_mongodb(self) -> Optional[MongoClient]:
        """Connect to MongoDB using environment variables"""
        mongodb_connection_string = os.getenv("MONGODB_CONNECTION_STRING")
        
        try:
            if mongodb_connection_string:
                connection_string = mongodb_connection_string
            else:
                # Build connection string from components
                mongodb_username = os.getenv("MONGODB_USERNAME")
                mongodb_password = os.getenv("MONGODB_PASSWORD")
                mongodb_cluster = os.getenv("MONGODB_CLUSTER")
                
                if not all([mongodb_username, mongodb_password, mongodb_cluster]):
                    print("MongoDB error: Missing required environment variables")
                    return None
                
                # Handle cluster name formatting
                if ".mongodb.net" in mongodb_cluster:
                    cluster_host = mongodb_cluster
                elif "." in mongodb_cluster and not mongodb_cluster.endswith(".net"):
                    cluster_host = f"{mongodb_cluster}.mongodb.net"
                else:
                    cluster_lower = mongodb_cluster.lower().replace(" ", "-")
                    cluster_host = f"{cluster_lower}.mongodb.net"
                
                database = os.getenv("MONGODB_DATABASE", "HackBrown")
                connection_string = f"mongodb+srv://{mongodb_username}:{mongodb_password}@{cluster_host}/{database}?retryWrites=true&w=majority"
            
            client = MongoClient(connection_string, serverSelectionTimeoutMS=10000)
            client.admin.command('ping')
            print("Successfully connected to MongoDB")
            return client
            
        except Exception as e:
            print(f"MongoDB connection error: {e}")
            return None
    
    def _setup_collections(self):
        """Create collections and indexes if they don't exist"""
        try:
            users_collection = self.db["users"]
            sessions_collection = self.db["sessions"]
            
            # Create unique index on email
            users_collection.create_index([("email", ASCENDING)], unique=True)
            users_collection.create_index([("username", ASCENDING)], unique=True)
            
            # Create index on session token
            sessions_collection.create_index([("token", ASCENDING)], unique=True)
            sessions_collection.create_index([("user_id", ASCENDING)])
            sessions_collection.create_index([("expires_at", ASCENDING)])
            
            print("MongoDB collections and indexes created successfully")
        except Exception as e:
            print(f"Error setting up collections: {e}")
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}${password_hash}"
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            salt, stored_hash = password_hash.split('$')
            password_check = hashlib.sha256((password + salt).encode()).hexdigest()
            return password_check == stored_hash
        except Exception as e:
            print(f"Error verifying password: {e}")
            return False
    
    def register_user(self, email: str, username: str, password: str, 
                     full_name: str = None) -> Tuple[bool, str]:
        """
        Register a new user in the system.
        
        Args:
            email: User's email address
            username: Desired username
            password: User's password (will be hashed)
            full_name: Optional full name
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.db:
            return False, "Database connection failed"
        
        # Validate inputs
        if not email or not username or not password:
            return False, "Email, username, and password are required"
        
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        
        if len(username) < 3:
            return False, "Username must be at least 3 characters"
        
        try:
            users_collection = self.db["users"]
            
            # Check if user already exists
            if users_collection.find_one({"email": email}):
                return False, "Email already registered"
            
            if users_collection.find_one({"username": username}):
                return False, "Username already taken"
            
            # Create new user document
            user_doc = {
                "email": email.lower(),
                "username": username,
                "password_hash": self.hash_password(password),
                "full_name": full_name or username,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_active": True,
                "preferences": {
                    "activity_categories": [],
                    "budget_range": None
                }
            }
            
            result = users_collection.insert_one(user_doc)
            return True, f"User registered successfully. User ID: {result.inserted_id}"
            
        except DuplicateKeyError:
            return False, "Email or username already exists"
        except Exception as e:
            print(f"Registration error: {e}")
            return False, f"Registration failed: {str(e)}"
    
    def login_user(self, username_or_email: str, password: str, 
                   remember_me: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate a user and create a session.
        
        Args:
            username_or_email: Username or email address
            password: User's password
            remember_me: If True, extend session expiry to 30 days
        
        Returns:
            Tuple of (success: bool, message: str, session_token: Optional[str])
        """
        if not self.db:
            return False, "Database connection failed", None
        
        try:
            users_collection = self.db["users"]
            
            # Find user by username or email
            user = users_collection.find_one({
                "$or": [
                    {"username": username_or_email},
                    {"email": username_or_email.lower()}
                ]
            })
            
            if not user:
                return False, "User not found", None
            
            if not user.get("is_active"):
                return False, "User account is inactive", None
            
            # Verify password
            if not self.verify_password(password, user["password_hash"]):
                # Log failed attempt
                self._log_login_attempt(user["_id"], success=False)
                return False, "Invalid password", None
            
            # Create session
            session_token = secrets.token_urlsafe(32)
            expires_in_days = 30 if remember_me else 7
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
            sessions_collection = self.db["sessions"]
            session_doc = {
                "token": session_token,
                "user_id": user["_id"],
                "username": user["username"],
                "email": user["email"],
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "last_activity": datetime.utcnow(),
                "remember_me": remember_me
            }
            
            sessions_collection.insert_one(session_doc)
            
            # Log successful login and update user's last login
            users_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"last_login": datetime.utcnow()},
                    "$inc": {"login_count": 1}
                }
            )
            
            return True, "Login successful", session_token
            
        except Exception as e:
            print(f"Login error: {e}")
            return False, f"Login failed: {str(e)}", None
    
    def verify_session(self, session_token: str) -> Tuple[bool, Optional[Dict]]:
        """
        Verify if a session token is valid.
        
        Args:
            session_token: The session token to verify
        
        Returns:
            Tuple of (is_valid: bool, user_data: Optional[Dict])
        """
        if not self.db:
            return False, None
        
        try:
            sessions_collection = self.db["sessions"]
            
            session = sessions_collection.find_one({"token": session_token})
            
            if not session:
                return False, None
            
            # Check if session has expired
            if datetime.utcnow() > session["expires_at"]:
                sessions_collection.delete_one({"token": session_token})
                return False, None
            
            # Update last activity
            sessions_collection.update_one(
                {"token": session_token},
                {"$set": {"last_activity": datetime.utcnow()}}
            )
            
            # Return user data (without sensitive info)
            user_data = {
                "user_id": str(session["user_id"]),
                "username": session["username"],
                "email": session["email"],
                "session_token": session_token,
                "expires_at": session["expires_at"].isoformat()
            }
            
            return True, user_data
            
        except Exception as e:
            print(f"Session verification error: {e}")
            return False, None
    
    def logout_user(self, session_token: str) -> bool:
        """
        Logout a user by invalidating their session token.
        
        Args:
            session_token: The session token to invalidate
        
        Returns:
            True if logout successful, False otherwise
        """
        if not self.db:
            return False
        
        try:
            sessions_collection = self.db["sessions"]
            result = sessions_collection.delete_one({"token": session_token})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Logout error: {e}")
            return False
    
    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        Get user profile information.
        
        Args:
            user_id: MongoDB ObjectId as string
        
        Returns:
            User profile dict or None if not found
        """
        if not self.db:
            return None
        
        try:
            from bson.objectid import ObjectId
            users_collection = self.db["users"]
            
            user = users_collection.find_one({"_id": ObjectId(user_id)})
            
            if not user:
                return None
            
            # Return profile without password hash
            return {
                "user_id": str(user["_id"]),
                "email": user["email"],
                "username": user["username"],
                "full_name": user.get("full_name"),
                "created_at": user["created_at"].isoformat(),
                "last_login": user.get("last_login", "Never").isoformat() if isinstance(user.get("last_login"), datetime) else "Never",
                "preferences": user.get("preferences", {}),
                "is_active": user.get("is_active", True)
            }
            
        except Exception as e:
            print(f"Error fetching user profile: {e}")
            return None
    
    def update_user_preferences(self, user_id: str, preferences: Dict) -> Tuple[bool, str]:
        """
        Update user preferences.
        
        Args:
            user_id: MongoDB ObjectId as string
            preferences: Dict with preference updates (e.g., activity_categories, budget_range)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.db:
            return False, "Database connection failed"
        
        try:
            from bson.objectid import ObjectId
            users_collection = self.db["users"]
            
            result = users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "preferences": preferences,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.matched_count == 0:
                return False, "User not found"
            
            return True, "Preferences updated successfully"
            
        except Exception as e:
            print(f"Error updating preferences: {e}")
            return False, f"Failed to update preferences: {str(e)}"
    
    def _log_login_attempt(self, user_id, success: bool):
        """Log login attempts for security tracking"""
        if not self.db:
            return
        
        try:
            login_logs_collection = self.db["login_logs"]
            log_doc = {
                "user_id": user_id,
                "success": success,
                "timestamp": datetime.utcnow()
            }
            login_logs_collection.insert_one(log_doc)
        except Exception as e:
            print(f"Error logging login attempt: {e}")
    
    def google_sign_in(self, google_token: str, 
                      remember_me: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate user via Google OAuth2 token.
        
        Args:
            google_token: ID token from Google OAuth2 (from frontend)
            remember_me: If True, extend session expiry to 30 days
        
        Returns:
            Tuple of (success: bool, message: str, session_token: Optional[str])
        """
        if not GOOGLE_AUTH_AVAILABLE:
            return False, "Google authentication not available", None
        
        if not self.db:
            return False, "Database connection failed", None
        
        try:
            # Verify Google token
            google_client_id = os.getenv("GOOGLE_CLIENT_ID")
            
            if not google_client_id:
                return False, "Google OAuth not configured", None
            
            # Verify the token with Google
            try:
                idinfo = id_token.verify_oauth2_token(
                    google_token, 
                    requests.Request(), 
                    google_client_id
                )
            except ValueError as e:
                print(f"Invalid Google token: {e}")
                return False, "Invalid Google token", None
            
            # Extract user information from token
            google_id = idinfo.get('sub')
            email = idinfo.get('email')
            full_name = idinfo.get('name', email)
            picture_url = idinfo.get('picture')
            
            if not google_id or not email:
                return False, "Invalid Google token data", None
            
            users_collection = self.db["users"]
            
            # Check if user exists with this email
            user = users_collection.find_one({"email": email.lower()})
            
            if user:
                # User already exists, just update last login
                if not user.get("is_active"):
                    return False, "User account is inactive", None
            else:
                # Create new user from Google data
                try:
                    user_doc = {
                        "email": email.lower(),
                        "username": email.split('@')[0],  # Use email prefix as username
                        "password_hash": None,  # No password for Google auth
                        "full_name": full_name,
                        "google_id": google_id,
                        "picture_url": picture_url,
                        "auth_method": "google",
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "is_active": True,
                        "preferences": {
                            "activity_categories": [],
                            "budget_range": None
                        }
                    }
                    result = users_collection.insert_one(user_doc)
                    user = user_doc
                    user["_id"] = result.inserted_id
                except DuplicateKeyError:
                    # Username conflict, use unique username with random suffix
                    unique_username = f"{email.split('@')[0]}{secrets.token_hex(4)}"
                    user_doc["username"] = unique_username
                    result = users_collection.insert_one(user_doc)
                    user = user_doc
                    user["_id"] = result.inserted_id
            
            # Create session
            session_token = secrets.token_urlsafe(32)
            expires_in_days = 30 if remember_me else 7
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
            sessions_collection = self.db["sessions"]
            session_doc = {
                "token": session_token,
                "user_id": user["_id"],
                "username": user["username"],
                "email": user["email"],
                "auth_method": "google",
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "last_activity": datetime.utcnow(),
                "remember_me": remember_me
            }
            
            sessions_collection.insert_one(session_doc)
            
            # Update user's last login
            users_collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {"last_login": datetime.utcnow()},
                    "$inc": {"login_count": 1}
                }
            )
            
            return True, "Google sign-in successful", session_token
            
        except Exception as e:
            print(f"Google sign-in error: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Google sign-in failed: {str(e)}", None
    
    def link_google_account(self, session_token: str, google_token: str) -> Tuple[bool, str]:
        """
        Link a Google account to an existing traditional auth user.
        
        Args:
            session_token: User's current session token
            google_token: Google OAuth2 ID token
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if not GOOGLE_AUTH_AVAILABLE:
            return False, "Google authentication not available"
        
        if not self.db:
            return False, "Database connection failed"
        
        try:
            # Verify current session
            is_valid, user_data = self.verify_session(session_token)
            if not is_valid or not user_data:
                return False, "Invalid session"
            
            # Verify Google token
            google_client_id = os.getenv("GOOGLE_CLIENT_ID")
            if not google_client_id:
                return False, "Google OAuth not configured"
            
            try:
                idinfo = id_token.verify_oauth2_token(
                    google_token,
                    requests.Request(),
                    google_client_id
                )
            except ValueError as e:
                return False, f"Invalid Google token: {e}"
            
            google_id = idinfo.get('sub')
            picture_url = idinfo.get('picture')
            
            if not google_id:
                return False, "Invalid Google token data"
            
            # Link Google account to user
            from bson.objectid import ObjectId
            users_collection = self.db["users"]
            
            result = users_collection.update_one(
                {"_id": ObjectId(user_data["user_id"])},
                {
                    "$set": {
                        "google_id": google_id,
                        "picture_url": picture_url,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.matched_count == 0:
                return False, "User not found"
            
            return True, "Google account linked successfully"
            
        except Exception as e:
            print(f"Error linking Google account: {e}")
            return False, f"Failed to link Google account: {str(e)}"


# Example usage
if __name__ == "__main__":
    # Initialize login manager
    login_manager = LoginManager()
    
    # Example: Register a new user
    print("\n--- Registering a new user ---")
    success, message = login_manager.register_user(
        email="john@example.com",
        username="john_doe",
        password="secure_password123",
        full_name="John Doe"
    )
    print(f"Registration: {message}")
    
    # Example: Login user
    if success:
        print("\n--- Logging in user ---")
        login_success, login_msg, token = login_manager.login_user(
            username_or_email="john_doe",
            password="secure_password123",
            remember_me=True
        )
        print(f"Login: {login_msg}")
        
        if login_success:
            print(f"Session token: {token}")
            
            # Example: Verify session
            print("\n--- Verifying session ---")
            is_valid, user_data = login_manager.verify_session(token)
            print(f"Session valid: {is_valid}")
            if user_data:
                print(f"User data: {json.dumps(user_data, indent=2)}")
            
            # Example: Get user profile
            print("\n--- Getting user profile ---")
            profile = login_manager.get_user_profile(user_data["user_id"])
            if profile:
                print(f"Profile: {json.dumps(profile, indent=2)}")
            
            # Example: Update preferences
            print("\n--- Updating user preferences ---")
            pref_success, pref_msg = login_manager.update_user_preferences(
                user_data["user_id"],
                {
                    "activity_categories": ["eat", "sightsee", "shop"],
                    "budget_range": {"min": 100, "max": 500}
                }
            )
            print(f"Preferences update: {pref_msg}")
            
            # Example: Logout
            print("\n--- Logging out user ---")
            logout_success = login_manager.logout_user(token)
            print(f"Logout successful: {logout_success}")
    
    # Example: Google Sign-In (requires GOOGLE_CLIENT_ID in .env)
    # In a real application, this would receive the token from the frontend
    # after the user completes Google OAuth2 flow
    print("\n--- Google Sign-In Example (requires valid Google token) ---")
    if GOOGLE_AUTH_AVAILABLE:
        print("Google Auth is available. Use google_sign_in() method with valid Google token.")
    else:
        print("Google Auth not available. Install google-auth: pip install google-auth")
