"""Small typed usage example; credential comes from the calling member, not source."""

import uuid
import httpx


class DataClient:
    def __init__(self,token,base_url="http://127.0.0.1:8001"):
        self.http=httpx.Client(base_url=base_url,headers={"Authorization":f"Bearer {token}"},timeout=60)

    def context(self,run_id,shop_id):
        response=self.http.get(f"/api/v1/runs/{run_id}/shops/{shop_id}/context")
        response.raise_for_status()
        return response.json()["data"]

    def command(self,path,body,*,idempotency_key):
        # The caller must reuse idempotency_key if a request needs a network retry.
        response=self.http.post(path,json=body,headers={"Idempotency-Key":idempotency_key,"X-Request-ID":uuid.uuid4().hex})
        response.raise_for_status()
        return response.json()["data"]

    def close(self):self.http.close()
