#!/usr/bin/env python3
"""
data-insight-kit 데이터 소스 어댑터 (중앙화된 read-only 경계).

connect 에이전트와 파이프라인은 DB 접근을 반드시 이 모듈을 통해서만 한다.
read-only 강제 + SELECT/WITH 전용 가드 + DuckDB→Polars 를 한 곳에 모은다.

설계 근거(계획 §10 #3·#4):
- DuckDB 가 기본 쿼리 엔진(수집·조인·집계). 결과는 Polars LazyFrame 으로 넘긴다.
- 연결은 항상 read_only=True (DuckDB 네이티브). 쓰기/DDL/DML/ATTACH/COPY/INSTALL 차단.
- 자격증명이 아니라 파일 경로가 민감정보 → 경로는 .env(DIK_DUCKDB_PATH), 커밋 금지.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys

import duckdb

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|install|load|"
    r"pragma|truncate|replace|merge|grant|revoke|vacuum|export|import)\b", re.I)


def _load_env(env_path: str | None = None) -> None:
    """connectors/.env 를 가볍게 읽어 os.environ 에 주입(python-dotenv 없이)."""
    p = pathlib.Path(env_path) if env_path else pathlib.Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def resolve_db_path(explicit: str | None = None) -> str:
    _load_env()
    path = explicit or os.environ.get("DIK_DUCKDB_PATH") or os.environ.get("VK_DUCKDB_PATH")
    if not path:
        raise RuntimeError("DB 경로 미설정 — connectors/.env 의 DIK_DUCKDB_PATH 또는 인자로 지정하세요.")
    if not pathlib.Path(path).exists():
        raise FileNotFoundError(f"DuckDB 파일 없음: {path} (외장 SSD 연결 확인)")
    return path


def connect(path: str | None = None) -> duckdb.DuckDBPyConnection:
    """항상 read-only 로 연결."""
    return duckdb.connect(resolve_db_path(path), read_only=True)


def _assert_select_only(sql: str) -> None:
    s = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.S | re.M).strip().rstrip(";").strip()
    head = s.split(None, 1)[0].lower() if s else ""
    if head not in ("select", "with"):
        raise ValueError(f"SELECT/WITH 쿼리만 허용 (받은 시작 토큰: '{head}')")
    if ";" in s:
        raise ValueError("다중 문장(;) 금지 — 단일 SELECT 만 허용")
    if _FORBIDDEN.search(s):
        raise ValueError("금지 키워드 감지 — read-only SELECT 만 허용")


def query_pl(sql: str, path: str | None = None, lazy: bool = True):
    """SELECT 결과를 Polars 로 반환. lazy=True 면 LazyFrame.

    대용량 자동 분기는 호출부(connect 에이전트)가 결정:
    작으면 그대로, 크면 .sink_parquet() 등으로 디스크 경유.
    """
    _assert_select_only(sql)
    con = connect(path)
    try:
        rel = con.sql(sql)            # 평가 지연 relation
        df = rel.pl()                 # → Polars DataFrame (Arrow 경유, pandas 안 거침)
        return df.lazy() if lazy else df
    finally:
        con.close()


def list_tables(path: str | None = None) -> list[str]:
    con = connect(path)
    try:
        return [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY 1").fetchall()]
    finally:
        con.close()


def snapshot_meta(path: str | None = None) -> dict:
    """manifest/lineage 용 freshness 메타데이터."""
    p = resolve_db_path(path)
    st = pathlib.Path(p).stat()
    return {
        "type": "duckdb",
        "ref": p,
        "file_mtime": datetime.datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(),
        "snapshot_at": datetime.datetime.now().astimezone().isoformat(),
        "read_only": True,
    }


if __name__ == "__main__":
    meta = snapshot_meta()
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    tabs = list_tables()
    print(f"\n테이블/뷰 {len(tabs)}개")
    if len(sys.argv) > 1:
        print(query_pl(sys.argv[1], lazy=False))
