"""Read/write smoke against a running local API, with a new isolated seller session."""

import argparse
import uuid
import httpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--base-url",default="http://127.0.0.1:8001");args=parser.parse_args()
    with httpx.Client(base_url=args.base_url,timeout=60) as client:
        def get(path):
            result=client.get(path);result.raise_for_status();return result.json()
        def post(path,body):
            result=client.post(path,json=body,headers={"Idempotency-Key":uuid.uuid4().hex});result.raise_for_status();return result.json()
        state=get("/api/state");print("run",state["run_id"])
        for day in range(1,8):
            post("/api/day/start",{})
            state=get("/api/state")
            if card:=state["pending_card"]:
                post("/api/decision",{"card_id":card["card_id"],"action":"accept",**({"rule_answer":True} if card["rule_question"] else {})})
                state=get("/api/state")
                if state["step"]=="content_review":
                    if day==1:post("/api/content/retry",{"feedback_vi":"Ảnh nền tối quá, làm sáng hơn giúp chị"})
                    post("/api/content/apply",{"cover_option":"B"})
            result=post("/api/night",{})
            assert result["next_day"]==(day+1 if day<7 else None)
            print(f"day {day}: PASS")
        state=get("/api/state");assert state["step"]=="complete"
        print("PASS: 7 ngày, không tạo ngày 8; không có API trả phí")


if __name__=="__main__":main()
