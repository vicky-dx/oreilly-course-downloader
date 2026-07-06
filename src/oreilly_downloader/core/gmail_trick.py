from .browsers import Logger
import os
import json
import datetime
import random
from typing import Optional, Dict, Any

class GmailTrickState:
    def get_unused_random_index(self) -> int:
        email = self.get_base_email()
        if not email or "@" not in email:
            raise ValueError("Invalid or missing base email in state.")
        local, domain = email.split("@", 1)
        domain_lower = domain.lower()
        is_gmail = "gmail.com" in domain_lower or "googlemail.com" in domain_lower
        
        if is_gmail:
            normalized_local = local.replace(".", "")
        else:
            normalized_local = local
            
        n = len(normalized_local)
        if n <= 1:
            return 0
            
        max_variations = 1 << (n - 1)
        
        # Build set of used indices from history
        used_indices = set()
        for h in self.state.get("history", []):
            used_indices.add(h.get("index"))
            
        # Exclude index 0 (clean base email) as requested
        used_indices.add(0)
        
        # Compile available indices
        available_indices = [i for i in range(1, max_variations) if i not in used_indices]
        
        if not available_indices:
            Logger.warning(" All dot-trick variations have been used. Recycling a random variation (excluding base email)...")
            return random.randint(1, max_variations - 1)
            
        return random.choice(available_indices)

    def __init__(self, output_dir: str):

        self.output_dir = output_dir
        self.state_file = os.path.join(output_dir, "signup_state.json")
        self.state: Dict[str, Any] = {
            "base_email": None,
            "next_index": 0,
            "history": []
        }
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                Logger.debug(f"Failed to load signup_state.json: {e}")

    def save(self):
        os.makedirs(self.output_dir, exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            Logger.debug(f"Failed to save signup_state.json: {e}")

    def get_base_email(self) -> Optional[str]:
        return self.state.get("base_email")

    def set_base_email(self, email: str):
        self.state["base_email"] = email
        self.save()

    def get_next_index(self) -> int:
        return self.state.get("next_index", 0)

    def increment_index(self):
        self.state["next_index"] = self.get_next_index() + 1
        self.save()

    def add_history(self, email: str, index: int, status: str, password: Optional[str] = None):
        if "history" not in self.state:
            self.state["history"] = []
        entry = {
            "index": index,
            "email": email,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status
        }
        if password:
            entry["password"] = password
        if status == "success":
            expiry = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
            entry["expires_at"] = expiry
        self.state["history"].append(entry)
        self.save()

    def get_active_valid_trial(self, base_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns the valid active trial account from history if present and not expired."""
        history = self.state.get("history", [])
        success_entries = [h for h in history if h.get("status") == "success"]
        if not success_entries:
            return None
            
        last_success = success_entries[-1]
        expires_at_str = last_success.get("expires_at")
        if not expires_at_str:
            return None
            
        expires_at = datetime.date.fromisoformat(expires_at_str)
        if datetime.date.today() > expires_at:
            return None
            
        # Verify that the active account email is a dot-trick variation of target base_email if provided
        if base_email:
            active_email = last_success.get("email")
            if not active_email or "@" not in active_email or "@" not in base_email:
                return None
            l1, d1 = active_email.split("@", 1)
            l2, d2 = base_email.split("@", 1)
            d1_norm = "gmail.com" if d1.lower() in ("gmail.com", "googlemail.com") else d1.lower()
            d2_norm = "gmail.com" if d2.lower() in ("gmail.com", "googlemail.com") else d2.lower()
            
            if l1.replace(".", "").lower() != l2.replace(".", "").lower() or d1_norm != d2_norm:
                return None
                
        return last_success



def get_dot_variation(email: str, index: int) -> str:
    if "@" not in email:
        raise ValueError("Invalid email address format.")
    local, domain = email.split("@", 1)
    
    domain_lower = domain.lower()
    is_gmail = "gmail.com" in domain_lower or "googlemail.com" in domain_lower
    
    if is_gmail:
        # Normalize local part by removing existing dots
        normalized_local = local.replace(".", "")
    else:
        normalized_local = local
        
    n = len(normalized_local)
    if n <= 1:
        return f"{normalized_local}@{domain}"
        
    max_variations = 1 << (n - 1)
    idx = index % max_variations
    
    result = []
    for i in range(n):
        result.append(normalized_local[i])
        if i < n - 1:
            if (idx >> i) & 1:
                result.append(".")
                
    return "".join(result) + "@" + domain
