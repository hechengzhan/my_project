import base64
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, desc, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(ROOT)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'campus_market.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CATEGORIES = {"数码", "书籍", "生活用品", "学习用品", "运动户外", "美妆服饰", "其他"}
SENSITIVE_WORDS = {"管制刀具", "违禁品", "毒品", "赌博", "枪支", "代考", "色情"}

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    listings: Mapped[list["Listing"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    price_low: Mapped[int] = mapped_column(Integer)
    price_high: Mapped[int] = mapped_column(Integer)
    condition: Mapped[str] = mapped_column(String(32))
    tags: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="on_sale", index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner: Mapped[User] = relationship(back_populates="listings")
    images: Mapped[list["ListingImage"]] = relationship(back_populates="listing", cascade="all, delete-orphan")


class ListingImage(Base):
    __tablename__ = "listing_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(255))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    listing: Mapped[Listing] = relationship(back_populates="images")


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(min_length=6, max_length=72)


class PublishPayload(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    category: str
    price_low: int = Field(ge=0, le=1_000_000)
    price_high: int = Field(ge=0, le=1_000_000)
    condition: str = Field(min_length=1, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=8)
    description: str = Field(min_length=5, max_length=1500)
    contact: str = Field(min_length=3, max_length=120)
    image_paths: list[str] = Field(min_length=1, max_length=3)


class StatusPayload(BaseModel):
    status: Literal["on_sale", "sold", "off_shelf"]


password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
app = FastAPI(title="青柠校园集 API", version="1.0.0")
origins = [item.strip() for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(user: User) -> str:
    payload = {"sub": str(user.id), "username": user.username, "admin": user.is_admin, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def user_from_credentials(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Annotated[Session, Depends(get_db)]) -> User:
    user = user_from_credentials(credentials, db)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return user


def user_out(user: User) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


def listing_out(item: Listing, detail: bool = False) -> dict:
    data = {
        "id": item.id, "title": item.title, "category": item.category,
        "price_low": item.price_low, "price_high": item.price_high, "condition": item.condition,
        "tags": [tag for tag in item.tags.split("|") if tag], "description": item.description,
        "status": item.status, "created_at": item.created_at.isoformat(), "owner": item.owner.username,
        "image_urls": [image.path for image in item.images],
    }
    if detail:
        data["contact"] = item.contact
        data["owner_id"] = item.owner_id
    return data


def contains_sensitive(text: str) -> str | None:
    normalized = text.lower().replace(" ", "")
    return next((word for word in SENSITIVE_WORDS if word in normalized), None)


def fallback_analysis(note: str) -> dict:
    lower = note.lower()
    if any(word in lower for word in ["书", "教材", "小说"]):
        category, title, low, high = "书籍", "九成新学习资料，等待新主人", 12, 35
    elif any(word in lower for word in ["耳机", "手机", "电脑", "键盘", "数码"]):
        category, title, low, high = "数码", "成色在线的实用数码好物", 80, 220
    else:
        category, title, low, high = "生活用品", "闲置好物，适合校园自提", 20, 65
    return {"title": title, "category": category, "condition": "九成新", "price_low": low, "price_high": high, "tags": ["高性价比", "校园自提", "实物拍摄"], "description": f"{title}，状态良好、使用正常。{note or '欢迎感兴趣的同学咨询细节'}，价格友好，校内当面验货自提更安心。", "source": "模拟估价（配置千问 API Key 后可启用真实视觉识别）"}


def qwen_analysis(file_paths: list[Path], note: str) -> dict:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return fallback_analysis(note)
    content = [{"type": "text", "text": "你是校园二手商品鉴定与估价助手。根据1-3张商品实拍图和补充说明，严格只返回JSON对象。字段为 title(不超过30字), category(必须是数码/书籍/生活用品/学习用品/运动户外/美妆服饰/其他之一), condition, price_low(整数), price_high(整数), tags(3到5个短标签数组), description(80到150字校园交易文案), violation(boolean), violation_reason(字符串)。如图片疑似违禁、色情、毒品、枪支或交易违法物品，violation=true。补充说明：" + (note or "无")}]
    for path in file_paths:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})
    client = OpenAI(api_key=api_key, base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    response = client.chat.completions.create(model=os.getenv("QWEN_MODEL", "qwen3.6-flash"), messages=[{"role": "user", "content": content}], temperature=0.2, response_format={"type": "json_object"})
    raw = response.choices[0].message.content or "{}"
    result = json.loads(raw)
    if result.get("violation"):
        raise HTTPException(status_code=400, detail=f"内容审核未通过：{result.get('violation_reason') or '疑似违规物品'}")
    category = result.get("category", "其他")
    result["category"] = category if category in CATEGORIES else "其他"
    result["price_low"] = max(0, int(result.get("price_low", 0)))
    result["price_high"] = max(result["price_low"], int(result.get("price_high", result["price_low"])))
    result["tags"] = [str(x)[:16] for x in result.get("tags", [])[:5]]
    result["source"] = "千问视觉 AI 估价"
    return result


@app.on_event("startup")
def initialize():
    if len(SECRET_KEY) < 32 or SECRET_KEY.startswith("请替换"):
        raise RuntimeError("请在 .env 中设置至少 32 位的 SECRET_KEY 后再启动项目")
    Base.metadata.create_all(bind=engine)
    expiry = datetime.now().timestamp() - 24 * 60 * 60
    for image in UPLOAD_DIR.glob("temp-*"):
        if image.is_file() and image.stat().st_mtime < expiry:
            image.unlink(missing_ok=True)
    with SessionLocal() as db:
        admin_name = os.getenv("ADMIN_USERNAME", "admin")
        if not db.scalar(select(User).where(User.username == admin_name)):
            db.add(User(username=admin_name, password_hash=password_hash.hash(os.getenv("ADMIN_PASSWORD", "Admin123!")), is_admin=True))
            db.commit()


@app.get("/api/health")
def health():
    return {"ok": True, "ai_enabled": bool(os.getenv("DASHSCOPE_API_KEY"))}


@app.post("/api/auth/register", status_code=201)
def register(payload: Credentials, db: Annotated[Session, Depends(get_db)]):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="该用户名已被注册")
    user = User(username=payload.username, password_hash=password_hash.hash(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user), "user": user_out(user)}


@app.post("/api/auth/login")
def login(payload: Credentials, db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    return {"token": create_token(user), "user": user_out(user)}


@app.get("/api/auth/me")
def me(user: Annotated[User, Depends(get_current_user)]):
    return user_out(user)


@app.post("/api/ai/analyze")
async def analyze(files: Annotated[list[UploadFile], File(...)], note: Annotated[str, Form()] = ""):
    if not 1 <= len(files) <= 3:
        raise HTTPException(status_code=400, detail="请上传 1 到 3 张图片")
    if len(note) > 300:
        raise HTTPException(status_code=400, detail="补充说明不能超过 300 个字符")
    bad_word = contains_sensitive(note)
    if bad_word:
        raise HTTPException(status_code=400, detail=f"补充说明含敏感词：{bad_word}")
    paths: list[Path] = []
    try:
        for upload in files:
            if upload.content_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WebP 图片")
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[upload.content_type]
            path = UPLOAD_DIR / f"temp-{uuid.uuid4().hex}{suffix}"
            content = await upload.read()
            if len(content) > 8 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="单张图片不能超过 8MB")
            path.write_bytes(content)
            paths.append(path)
        result = qwen_analysis(paths, note)
        result["image_paths"] = [f"/uploads/{path.name}" for path in paths]
        return result
    except HTTPException:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        for path in paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"AI 估价服务暂时不可用：{str(exc)[:120]}")


@app.post("/api/listings", status_code=201)
def publish(payload: PublishPayload, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="商品分类无效")
    if payload.price_low > payload.price_high:
        raise HTTPException(status_code=400, detail="价格下限不能高于上限")
    bad_word = contains_sensitive(" ".join([payload.title, payload.description]))
    if bad_word:
        raise HTTPException(status_code=400, detail=f"发布内容含敏感词：{bad_word}")
    allowed_paths = []
    for url in payload.image_paths:
        match = re.fullmatch(r"/uploads/(temp-[a-f0-9]+\.(?:jpg|png|webp))", url)
        if not match or not (UPLOAD_DIR / match.group(1)).exists():
            raise HTTPException(status_code=400, detail="图片已失效，请重新进行 AI 估价")
        source = UPLOAD_DIR / match.group(1)
        final_name = source.name.replace("temp-", "item-", 1)
        source.rename(UPLOAD_DIR / final_name)
        allowed_paths.append(f"/uploads/{final_name}")
    item = Listing(title=payload.title, category=payload.category, price_low=payload.price_low, price_high=payload.price_high, condition=payload.condition, tags="|".join(payload.tags), description=payload.description, contact=payload.contact, owner_id=user.id)
    item.images = [ListingImage(path=path) for path in allowed_paths]
    db.add(item)
    db.commit()
    db.refresh(item)
    return listing_out(item, detail=True)


@app.get("/api/listings")
def list_listings(page: int = 1, page_size: int = 12, category: str | None = None, keyword: str | None = None, db: Session = Depends(get_db)):
    page, page_size = max(page, 1), min(max(page_size, 1), 30)
    query = select(Listing).order_by(desc(Listing.created_at))
    if category and category in CATEGORIES:
        query = query.where(Listing.category == category)
    if keyword:
        escaped = f"%{keyword.strip()}%"
        query = query.where(or_(Listing.title.like(escaped), Listing.description.like(escaped)))
    query = query.where(Listing.status.in_(["on_sale", "sold"]))
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [listing_out(item) for item in items], "page": page, "has_more": len(items) == page_size}


@app.get("/api/listings/mine")
def my_listings(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    items = db.scalars(select(Listing).where(Listing.owner_id == user.id).order_by(desc(Listing.created_at))).all()
    return [listing_out(item, detail=True) for item in items]


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Annotated[Session, Depends(get_db)]):
    item = db.get(Listing, listing_id)
    viewer = user_from_credentials(credentials, db)
    can_view_off_shelf = viewer and (viewer.is_admin or viewer.id == item.owner_id) if item else False
    if not item or (item.status == "off_shelf" and not can_view_off_shelf):
        raise HTTPException(status_code=404, detail="商品不存在或已下架")
    return listing_out(item, detail=True)


@app.patch("/api/listings/{listing_id}/status")
def update_status(listing_id: int, payload: StatusPayload, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    item = db.get(Listing, listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在")
    if item.owner_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="只能管理自己发布的商品")
    item.status = payload.status
    db.commit()
    db.refresh(item)
    return listing_out(item, detail=True)


def delete_listing_and_images(item: Listing, db: Session) -> None:
    for image in item.images:
        (UPLOAD_DIR / Path(image.path).name).unlink(missing_ok=True)
    db.delete(item)
    db.commit()


@app.delete("/api/listings/{listing_id}")
def delete_own_listing(listing_id: int, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    item = db.get(Listing, listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在")
    if item.owner_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己发布的商品")
    delete_listing_and_images(item, db)
    return {"ok": True}


@app.delete("/api/admin/listings/{listing_id}")
def delete_listing(listing_id: int, admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)]):
    item = db.get(Listing, listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在")
    delete_listing_and_images(item, db)
    return {"ok": True}


DIST_DIR = ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        target = DIST_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
