"""Canonical five-shop dataset, labeled knowledge and PNG placeholders."""

from pathlib import Path
import hashlib
import json
import struct
import zlib
from .simulation import business_date, channel_metrics
from .storage import insert, now, timestamps


TITLE = "Quạt mini cầm tay sạc usb loại tốt giá rẻ"
DESCRIPTION = "Quạt mini cầm tay. Sạc usb. 3 tốc độ gió. Pin 2000mAh. Có 3 màu."
ATTRIBUTES = ["3 tốc độ gió", "sạc USB", "pin 2000mAh", "3 màu: Trắng, Hồng, Xanh mint"]
DESKTOP_TITLE = 'Quạt để bàn màu trắng'
DESKTOP_DESCRIPTION = 'Quạt để bàn màu trắng, cánh màu xanh nhạt, có đế và núm điều chỉnh.'
DESKTOP_ATTRIBUTES = ['quạt để bàn', 'thân màu trắng', 'cánh màu xanh nhạt', 'có đế', 'có núm điều chỉnh']


def world():
    shops = {}
    rows = [
        ("A","Quạt Xinh Official","anh Minh",189000,110000,400,.45,3,3000,100000,10,30000),
        ("B","Gió Mát Store","chị Hoa",129000,112000,250,.35,4,2000,0,5,12000),
        ("C","Tiện Ích 24h","anh Tuấn",159000,95000,15,.40,3,1500,80000,10,25000),
        ("D","Nhà Bé Lan","chị Lan",175000,115000,300,.55,3,2500,45000,8,18000),
        ("E","Mát Lạnh Shop","anh Phúc",99000,60000,350,.50,2,2200,50000,5,15000),
    ]
    for i,(sid,name,owner,price,cost,stock,q,rank,impr,cap,voucher,profit) in enumerate(rows,1):
        title,description,attributes=(DESKTOP_TITLE,DESKTOP_DESCRIPTION,DESKTOP_ATTRIBUTES) if sid=='D' else (TITLE,DESCRIPTION,ATTRIBUTES)
        shops[sid] = {"product_id":f"SP00{i}","public":dict(shop_id=sid,name=name,category="quat_mini",price=price,
            stock=stock,listing_quality=q,search_rank_page=rank,rating=4.6,base_impressions=impr,
            title=title,description=description,attributes=attributes,images=[],video=None,active_voucher_pct=0),
            "private":{"owner_name":owner,"unit_cost":cost,"rules":dict(allow_ads=sid!="B",ads_daily_max=cap,
                voucher_max_pct=voucher,min_profit_per_unit=profit,max_breakeven_roas=6.5,
                require_stop_condition=True,content_style_notes=[])},
            "persona":{"hidden_voucher_comfort_pct":5 if sid=="A" else None,
                       "content_style_pref":"nền sáng" if sid=="D" else None,"accepts_ads":sid!="B"}}
    return {"shops":shops,"start_date":"2026-11-01","scenario_version":"demo-v1",
            "fees":{"fixed_pct":8,"transaction_pct":5,"tax_pct":1.5,"per_order":3000},
            "trend":{"keyword":"quạt mini cầm tay","growth_7d_pct":240},
            "calendar":[{"name":"11.11","date":"2026-11-11"}]}


def placeholder_png(index):
    def chunk(kind, content):
        return struct.pack(">I",len(content))+kind+content+struct.pack(">I",zlib.crc32(kind+content)&0xffffffff)
    # Deliberately a small geometric placeholder, not a claimed product photograph.
    pixels = b"".join(b"\x00" + bytes((45+index*20,65,95))*64 for _ in range(64))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",64,64,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b"")


def prepare(root):
    root = Path(root)
    documents = root / "knowledge"
    documents.mkdir(parents=True,exist_ok=True)
    sources = {
        "selling_policy_demo":("selling_policy","Chính sách bán hàng", "Thông tin sản phẩm phải đúng thuộc tính. Người bán duyệt gói trước khi chi quảng cáo. Không tự tăng chi, không tự đổi luật."),
        "fee_calculation_guide_demo":("fee_guide","Hướng dẫn phí", "Phí giả định: 8% cố định + 5% giao dịch + 1,5% thuế trên giá sau voucher; cộng 3.000đ/đơn. Lãi/đơn = giá sau voucher × 0,855 − 3.000đ − giá vốn. ROAS thực = doanh thu paid / chi paid; không chi thì null. Lãi này chưa gồm vận hành và chi phí tạo nội dung. Ví dụ sản phẩm 175.000đ voucher 3% có giá sau voucher 169.750đ; phí làm tròn từng kênh, lãi/đơn làm tròn half-up và ghi sai lệch làm tròn riêng."),
        "advertising_guide_demo":("ads_guide","Hướng dẫn quảng cáo", "CPC giả định 1.800đ. Ngân sách ngày 0 hoặc tối thiểu 10.000đ, tổng tối đa bằng ngân sách ngày × thời hạn. Theo dõi ROAS paid; hai ngày thấp hơn ngưỡng đã duyệt thì dừng trước chi ngày tiếp. Dừng ads không hủy voucher hoặc nội dung."),
        "content_standards_demo":("content_policy","Tiêu chuẩn nội dung", "Tiêu đề tối đa 120 ký tự; mô tả tối đa 5.000 ký tự. Không bịa thương hiệu, bảo hành, độ ồn hoặc thời lượng pin. Ảnh giữ hình dáng sản phẩm, không chữ/logo. Ba bản nội dung tổng cộng; người bán chọn và duyệt trước xuất bản."),
    }
    for sid,shop in world()["shops"].items():
        sources[f'product_{shop["product_id"]}']=("product",shop["public"]["name"],shop['public']['description']+"\n\n"+"\n".join(shop['public']['attributes'])+"\n\nThương hiệu, bảo hành, kích thước, độ ồn và thông số kỹ thuật: chưa xác minh.")
    manifest = {"scenario_version":"demo-v1","schema_version":1,"simulator_version":"market-v1","seed":42,
                "history_days":14,"simulation_days":7,"synthetic":True,"proof_of_learning":False,"files":{}}
    for name,(kind,title,text) in sources.items():
        content=f"---\ndocument_id: {name}\ndocument_type: {kind}\nversion: 1\neffective_from: 2026-10-18\nis_simulated: true\n---\n\n# {title}\n\nSimulation material for this hackathon; not an official Shopee policy.\n\n{text}\n"
        path=documents/f"{name}.md"
        path.write_text(content,encoding="utf-8")
        manifest["files"][str(path.relative_to(root))]={"sha256":hashlib.sha256(content.encode()).hexdigest(),"access":"public"}
    for i,sid in enumerate("ABCDE",1):
        path=root/"originals"/f"{sid}-placeholder.png"
        path.parent.mkdir(exist_ok=True)
        content=placeholder_png(i)
        path.write_bytes(content)
        manifest["files"][str(path.relative_to(root))]={"sha256":hashlib.sha256(content).hexdigest(),"access":"public","is_placeholder":True}
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    return manifest


def seed_shared(c, root):
    prepare(root)
    for code,rate,fixed in (("fixed",800,None),("transaction",500,None),("tax",150,None),("order",None,3000)):
        c.execute("INSERT OR IGNORE INTO fee_rules VALUES (?,?,?,?,?,?,?,?,?,?)",("demo-fees-v1",code,"rate" if rate else "fixed_per_order",rate,fixed,"net_item_revenue" if rate else "fulfilled_order","quat_mini","2026-10-18",None,1))
    for code,params in (("MIN_STOCK",{"value":30}),("ADS_MIN_DAILY",{"value":10000}),("MAX_ROUNDS",{"value":3})):
        c.execute("INSERT OR IGNORE INTO platform_rules VALUES (?,?,?,?,?,?,?,?)",("demo-policy-v1",code,code,json.dumps(params),"block","2026-10-18",None,1))
    for path in sorted((Path(root)/"knowledge").glob("*.md")):
        kind=next(line.split(': ',1)[1] for line in path.read_text(encoding='utf-8').splitlines() if line.startswith('document_type: '))
        c.execute("INSERT OR IGNORE INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
            path.stem,1,kind,path.stem,"shared",None,None,
            str(path.relative_to(root)),None,None,"ready","2026-10-18",None,1,None,None,hashlib.sha256(path.read_bytes()).hexdigest(),"knowledge-v1",now()))
        c.execute("UPDATE knowledge_documents SET type=?,checksum=? WHERE document_id=? AND document_version=1 AND source_object_key=?",(kind,hashlib.sha256(path.read_bytes()).hexdigest(),path.stem,str(path.relative_to(root))))


def seed_run(c, run_id, root, seed, product_image_path=None):
    from .storage import uid
    for sid,shop in world()["shops"].items():
        p,priv=shop["public"],shop["private"]
        pid=shop["product_id"]
        insert(c,"shops",run_id=run_id,shop_id=sid,name=p["name"],category=p["category"],description="Shop giả lập",status="active",**timestamps())
        facts={'product_kind':'desktop_fan' if sid=='D' else 'handheld_fan','verified_claims':[{'claim_id':str(i),'text_vi':v,'source_reference':'source-image:desktop-fan' if sid=='D' else 'seed:demo-v1'} for i,v in enumerate(p['attributes'])]}
        if sid!='D': facts.update(colors=['Trắng','Hồng','Xanh mint'],battery_capacity_mah=2000,speed_levels=3,included_items=[])
        insert(c,"products",run_id=run_id,product_id=pid,shop_id=sid,name="Quạt để bàn" if sid=='D' else "Quạt mini cầm tay",list_price_vnd=p["price"],
               facts_json=facts,listing_quality=p["listing_quality"],search_rank_page=p["search_rank_page"],rating=4.6,base_impressions=p["base_impressions"],active_content_id=None,status="active",**timestamps())
        insert(c,"product_costs",run_id=run_id,product_id=pid,cost_version=1,unit_cost_vnd=priv["unit_cost"],other_unit_cost_vnd=0,effective_day=-13,created_at=now())
        insert(c,"inventory",run_id=run_id,product_id=pid,available_units=p["stock"],**timestamps())
        r=priv["rules"]
        insert(c,"shop_rules",run_id=run_id,shop_id=sid,rules_version=1,allow_ads=r["allow_ads"],ads_cap_daily_vnd=r["ads_daily_max"],ads_cap_package_vnd=None,voucher_max_pct=r["voucher_max_pct"],min_profit_per_unit_vnd=r["min_profit_per_unit"],max_breakeven_roas=6.5,require_stop_condition=True,minimum_campaign_stock=30,content_style_notes_json=[],effective_day=-13,confirmed_by="seed_admin",confirmed_at=now(),confirmation_decision_id=None)
        path=Path(root)/"originals"/f"{sid}-placeholder.png"
        source='generated_geometric_placeholder_not_product_photo';mime='image/png';width=height=64
        if sid=='D' and product_image_path:
            raw=Path(product_image_path).read_bytes()
            if not raw.startswith(b'\xff\xd8\xff') or len(raw)>10*1024*1024: raise ValueError('Invalid desktop product image')
            path=Path(root)/'originals'/run_id/'desktop-product.jpg';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            source='local_import:sha256:'+hashlib.sha256(raw).hexdigest();mime='image/jpeg';width=height=None
        aid=uid("asset")
        insert(c,"assets",run_id=run_id,asset_id=aid,shop_id=sid,product_id=pid,kind="image",object_key=str(path.relative_to(root)),mime_type=mime,size_bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),width=width,height=height,duration_seconds=None,origin="supplied",source_reference=source,visibility="published",upload_status="ready",upload_owner="seed_admin",created_at=now())
        cid=uid("content")
        insert(c,"content_versions",run_id=run_id,content_id=cid,product_id=pid,content_version=1,parent_content_id=None,title=p['title'],description=p['description'],cover_options_json=[],video_job_json={},feedback_history_json=[],style_notes_json=[],cover_asset_id=aid,video_asset_id=None,quality_gain=0,published_day=-13,validation_json=['Nguồn ảnh: '+source],status="published",**timestamps())
        c.execute("UPDATE products SET active_content_id=? WHERE run_id=? AND product_id=?",(cid,run_id,pid))
        insert(c,"shop_runtime",run_id=run_id,shop_id=sid,cooldown_until_day=0,seller_renegotiations=0,active_negotiation_id=None,pending_card_id=None,**timestamps())
        for day in range(-13,1):
            for m in channel_metrics(p,priv["unit_cost"],seed=seed,day=day,stock=p["stock"],quality=p["listing_quality"]):
                insert(c,"daily_metrics",run_id=run_id,product_id=pid,date=business_date(day),day=day,shop_id=sid,campaign_id=None,content_id=cid,fee_policy_version="demo-fees-v1",cost_version=1,settlement_id=None,source="seeded",created_at=now(),**m)
    for day in range(-13,1):
        insert(c,"market_daily",run_id=run_id,date=business_date(day),keyword="quạt mini cầm tay",search_volume=10000,qualified_listing_count=5,benchmark_cpc_vnd=1800,benchmark_ctr_bps=250,benchmark_cvr_bps=500,observed_at=business_date(day)+"T00:00:00+07:00")
    insert(c,"run_policies",run_id=run_id,fee_policy_version="demo-fees-v1",platform_policy_version="demo-policy-v1",knowledge_release="knowledge-v1",created_at=now())
