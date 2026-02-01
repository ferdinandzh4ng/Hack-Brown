"""
Login system for Hack-Brown with MongoDB integration.
Handles user authentication, registration, session management, and Google OAuth2 sign-in.
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
try:
    from cryptography.fernet import Fernet
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    print("Warning: cryptography library not installed. Payment data will use hashing instead of encryption.")
import base64

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
            payment_methods_collection = self.db["payment_methods"]
            
            # Create unique index on email
            users_collection.create_index([("email", ASCENDING)], unique=True)
            users_collection.create_index([("username", ASCENDING)], unique=True)
            
            # Create index on session token
            sessions_collection.create_index([("token", ASCENDING)], unique=True)
            sessions_collection.create_index([("user_id", ASCENDING)])
            sessions_collection.create_index([("expires_at", ASCENDING)])
            
            # Create indexes for payment methods
            payment_methods_collection.create_index([("user_id", ASCENDING)])
            payment_methods_collection.create_index([("user_id", ASCENDING), ("is_default", ASCENDING)])
            
            print("MongoDB collections and indexes created successfully")
        except Exception as e:
            print(f"Error setting up collections: {e}")
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key for payment methods"""
        key_env = os.getenv("PAYMENT_ENCRYPTION_KEY")
        if key_env:
            # Use provided key (should be base64 encoded)
            try:
                return base64.urlsafe_b64decode(key_env.encode())
            except:
                # If not base64, use as-is (32 bytes)
                return key_env.encode()[:32].ljust(32, b'0')
        else:
            # Generate a key (in production, this should be set in env)
            # For development, generate a deterministic key
            key = hashlib.sha256(b"HackBrownPaymentKey2024").digest()
            return key
    
    def _encrypt_payment_data(self, data: str) -> str:
        """Encrypt payment method data"""
        if not CRYPTOGRAPHY_AVAILABLE:
            # Fallback: hash instead of encrypt (less secure but works)
            return hashlib.sha256(data.encode()).hexdigest()
        
        try:
            key = self._get_encryption_key()
            f = Fernet(base64.urlsafe_b64encode(key))
            encrypted = f.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            print(f"Encryption error: {e}")
            # Fallback: hash instead of encrypt (less secure but works)
            return hashlib.sha256(data.encode()).hexdigest()
    
    def _decrypt_payment_data(self, encrypted_data: str) -> str:
        """Decrypt payment method data"""
        if not CRYPTOGRAPHY_AVAILABLE:
            # Cannot decrypt if we only hashed
            return ""
        
        try:
            key = self._get_encryption_key()
            f = Fernet(base64.urlsafe_b64encode(key))
            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = f.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            print(f"Decryption error: {e}")
            return ""
    
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
        if self.db is None:
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
                "onboarding_completed": False,
                "preferences": {
                    "activity_categories": [],
                    "favorite_stores": [],
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
        if self.db is None:
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
        if self.db is None:
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
        if self.db is None:
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
        if self.db is None:
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
                "onboarding_completed": user.get("onboarding_completed", False),
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
            preferences: Dict with preference updates (e.g., activity_categories, favorite_stores, budget_range, onboarding_completed)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if self.db is None:
            return False, "Database connection failed"
        
        try:
            from bson.objectid import ObjectId
            users_collection = self.db["users"]
            
            # Separate onboarding_completed from preferences if present
            update_data = {"updated_at": datetime.utcnow()}
            
            if "onboarding_completed" in preferences:
                update_data["onboarding_completed"] = preferences.pop("onboarding_completed")
            
            # Update preferences
            if preferences:
                # Merge with existing preferences
                user = users_collection.find_one({"_id": ObjectId(user_id)})
                if user:
                    existing_prefs = user.get("preferences", {})
                    existing_prefs.update(preferences)
                    update_data["preferences"] = existing_prefs
                else:
                    update_data["preferences"] = preferences
            
            result = users_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                return False, "User not found"
            
            return True, "Preferences updated successfully"
            
        except Exception as e:
            print(f"Error updating preferences: {e}")
            return False, f"Failed to update preferences: {str(e)}"
    
    def _log_login_attempt(self, user_id, success: bool):
        """Log login attempts for security tracking"""
        if self.db is None:
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
        
        if self.db is None:
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
                        "onboarding_completed": False,
                        "preferences": {
                            "activity_categories": [],
                            "favorite_stores": [],
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
        
        if self.db is None:
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
    
    def add_payment_method(self, user_id: str, card_number: str, expiry_date: str, 
                          cardholder_name: str, cvv: str, billing_address: Optional[Dict] = None,
                          is_default: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Add a payment method for a user (encrypted storage).
        
        Args:
            user_id: MongoDB ObjectId as string
            card_number: Credit card number (will be encrypted)
            expiry_date: Card expiry date (MM/YY)
            cardholder_name: Name on card
            cvv: CVV code (will be encrypted)
            billing_address: Optional billing address dict
            is_default: Whether this should be the default payment method
        
        Returns:
            Tuple of (success: bool, message: str, payment_method_id: Optional[str])
        """
        if self.db is None:
            return False, "Database connection failed", None
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            # Encrypt sensitive data
            encrypted_card = self._encrypt_payment_data(card_number)
            encrypted_cvv = self._encrypt_payment_data(cvv)
            
            # If this is set as default, unset other defaults
            if is_default:
                payment_methods_collection.update_many(
                    {"user_id": ObjectId(user_id), "is_default": True},
                    {"$set": {"is_default": False}}
                )
            
            # Store last 4 digits for display (not encrypted)
            last_4 = card_number[-4:] if len(card_number) >= 4 else "****"
            
            payment_method = {
                "user_id": ObjectId(user_id),
                "card_number_encrypted": encrypted_card,
                "cvv_encrypted": encrypted_cvv,
                "expiry_date": expiry_date,
                "cardholder_name": cardholder_name,
                "last_4": last_4,
                "billing_address": billing_address or {},
                "is_default": is_default,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = payment_methods_collection.insert_one(payment_method)
            payment_method_id = str(result.inserted_id)
            
            return True, "Payment method added successfully", payment_method_id
            
        except Exception as e:
            print(f"Error adding payment method: {e}")
            return False, f"Failed to add payment method: {str(e)}", None
    
    def get_payment_methods(self, user_id: str) -> List[Dict]:
        """
        Get all payment methods for a user (decrypted for display).
        
        Args:
            user_id: MongoDB ObjectId as string
        
        Returns:
            List of payment method dicts (with masked card numbers)
        """
        if self.db is None:
            return []
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            methods = list(payment_methods_collection.find(
                {"user_id": ObjectId(user_id)},
                {"card_number_encrypted": 0, "cvv_encrypted": 0}  # Don't return encrypted data
            ).sort("is_default", -1))
            
            # Convert ObjectId to string and format for frontend
            result = []
            for method in methods:
                result.append({
                    "id": str(method["_id"]),
                    "last_4": method.get("last_4", "****"),
                    "expiry_date": method.get("expiry_date", ""),
                    "cardholder_name": method.get("cardholder_name", ""),
                    "billing_address": method.get("billing_address", {}),
                    "is_default": method.get("is_default", False),
                    "created_at": method.get("created_at", datetime.utcnow()).isoformat() if isinstance(method.get("created_at"), datetime) else None
                })
            
            return result
            
        except Exception as e:
            print(f"Error getting payment methods: {e}")
            return []
    
    def delete_payment_method(self, user_id: str, payment_method_id: str) -> Tuple[bool, str]:
        """
        Delete a payment method.
        
        Args:
            user_id: MongoDB ObjectId as string
            payment_method_id: Payment method ObjectId as string
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if self.db is None:
            return False, "Database connection failed"
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            result = payment_methods_collection.delete_one({
                "_id": ObjectId(payment_method_id),
                "user_id": ObjectId(user_id)
            })
            
            if result.deleted_count == 0:
                return False, "Payment method not found"
            
            return True, "Payment method deleted successfully"
            
        except Exception as e:
            print(f"Error deleting payment method: {e}")
            return False, f"Failed to delete payment method: {str(e)}"
    
    def set_default_payment_method(self, user_id: str, payment_method_id: str) -> Tuple[bool, str]:
        """
        Set a payment method as default.
        
        Args:
            user_id: MongoDB ObjectId as string
            payment_method_id: Payment method ObjectId as string
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        if self.db is None:
            return False, "Database connection failed"
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            # Unset all other defaults
            payment_methods_collection.update_many(
                {"user_id": ObjectId(user_id), "is_default": True},
                {"$set": {"is_default": False}}
            )
            
            # Set this one as default
            result = payment_methods_collection.update_one(
                {"_id": ObjectId(payment_method_id), "user_id": ObjectId(user_id)},
                {"$set": {"is_default": True, "updated_at": datetime.utcnow()}}
            )
            
            if result.matched_count == 0:
                return False, "Payment method not found"
            
            return True, "Default payment method updated successfully"
            
        except Exception as e:
            print(f"Error setting default payment method: {e}")
            return False, f"Failed to set default payment method: {str(e)}"
    
    def has_payment_methods(self, user_id: str) -> bool:
        """
        Check if user has any payment methods.
        
        Args:
            user_id: MongoDB ObjectId as string
        
        Returns:
            True if user has at least one payment method
        """
        if self.db is None:
            return False
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            count = payment_methods_collection.count_documents({"user_id": ObjectId(user_id)})
            return count > 0
            
        except Exception as e:
            print(f"Error checking payment methods: {e}")
            return False
    
    def get_default_payment_method_for_processing(self, user_id: str) -> Optional[Dict]:
        """
        Get the default payment method with decrypted card details for payment processing.
        WARNING: Only use this for actual payment processing, not for display.
        
        Args:
            user_id: MongoDB ObjectId as string
            
        Returns:
            Dict with decrypted card details or None if no payment method found
        """
        if self.db is None:
            return None
        
        try:
            from bson.objectid import ObjectId
            payment_methods_collection = self.db["payment_methods"]
            
            # Get default payment method, or first one if no default
            method = payment_methods_collection.find_one(
                {"user_id": ObjectId(user_id), "is_default": True}
            )
            
            if not method:
                # Get first payment method if no default
                method = payment_methods_collection.find_one(
                    {"user_id": ObjectId(user_id)}
                )
            
            if not method:
                return None
            
            # Decrypt card details
            card_number = self._decrypt_payment_data(method.get("card_number_encrypted", ""))
            cvv = self._decrypt_payment_data(method.get("cvv_encrypted", ""))
            
            if not card_number or not cvv:
                return None
            
            return {
                "payment_method_id": str(method["_id"]),
                "card_number": card_number,
                "cvv": cvv,
                "expiry_date": method.get("expiry_date", ""),
                "cardholder_name": method.get("cardholder_name", ""),
                "billing_address": method.get("billing_address", {}),
                "last_4": method.get("last_4", card_number[-4:] if len(card_number) >= 4 else "****")
            }
            
        except Exception as e:
            print(f"Error getting payment method for processing: {e}")
            return None


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
