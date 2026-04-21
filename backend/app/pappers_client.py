"""
Pappers.fr API client for fetching French company/association board members.

API docs: https://www.pappers.fr/api
Requires API key from Pappers.fr (paid service, ~€29-99/month)

Usage:
    client = PappersClient(api_key="your_key")
    board = client.get_board_members(siret="12345678900010")
"""

import requests
import time
from typing import List, Dict, Optional

PAPPERS_API_BASE = "https://api.pappers.fr/v2"

class PappersClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    def get_company(self, siret: str) -> Optional[Dict]:
        """Fetch company details by SIRET"""
        url = f"{PAPPERS_API_BASE}/entreprise"
        params = {
            "siret": siret.replace(" ", ""),
            "api_token": self.api_key
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                print(f"Rate limited on {siret}, waiting...")
                time.sleep(2)
                return self.get_company(siret)
            else:
                print(f"Pappers error {resp.status_code} for {siret}: {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"Exception fetching {siret}: {e}")
            return None
    
    def get_board_members(self, siret: str) -> List[Dict]:
        """Extract board members from company data"""
        data = self.get_company(siret)
        if not data:
            return []
        
        members = []
        
        # Pappers returns dirigeants (directors) and représentants
        dirigeants = data.get("dirigeants", [])
        for d in dirigeants:
            members.append({
                "name": f"{d.get('nom', '')} {d.get('prenom', '')}".strip(),
                "role": d.get("qualite", "Dirigeant"),
                "source": "Pappers.fr",
                "date_naissance": d.get("date_de_naissance"),
            })
        
        # Also check représentants
        representants = data.get("representants", [])
        for r in representants:
            members.append({
                "name": f"{r.get('nom', '')} {r.get('prenom', '')}".strip(),
                "role": r.get("qualite", "Représentant"),
                "source": "Pappers.fr",
            })
        
        return members
    
    def enrich_associations(self, sirets: List[str], delay: float = 0.5) -> Dict[str, List[Dict]]:
        """Batch enrich multiple associations"""
        results = {}
        for siret in sirets:
            members = self.get_board_members(siret)
            if members:
                results[siret] = members
            time.sleep(delay)  # Rate limiting
        return results
