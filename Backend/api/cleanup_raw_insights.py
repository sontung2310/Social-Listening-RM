from datetime import datetime, timedelta, timezone
from typing import Set, Dict, List, Tuple
from bson import ObjectId
from db.persist import get_mongo_db


def cleanup_raw_insights(days_threshold: int = 7, dry_run: bool = True) -> None:
    """
    Clean up raw_insights that are safe to remove.

    Logic:
      1) Find histories where ai_ready == true AND created_at < (now - days_threshold).
      2) For each such history, collect its ai_results (pull raw_id/url).
      3) A raw_insights doc is deletable only if there is NO ai_results in ANY OTHER
         history that still references that raw_id (or the same url when raw_id is missing).
      4) In dry_run mode, just print what would be deleted. If dry_run=False, delete them.

    NOTE:
      - We never touch ai_results here, only raw_insights.
    """

    db = get_mongo_db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)

    # 1) histories eligible for cleanup
    ready_histories = list(
        db["history"].find(
            {"ai_ready": True, "created_at": {"$lt": cutoff}},
            {"_id": 1, "subject": 1, "created_at": 1},
        )
    )
    if not ready_histories:
        print("No eligible histories found for cleanup.")
        return

    eligible_hids: Set[ObjectId] = {h["_id"] for h in ready_histories}
    print(f"Found {len(ready_histories)} processed histories older than {days_threshold} days.")

    # 2) collect candidate raw_ids/urls from those histories' ai_results
    candidates_raw_ids: Set[ObjectId] = set()
    candidates_urls: Set[str] = set()

    for h in ready_histories:
        hid = h["_id"]
        # pull minimal fields to avoid large payload
        cursor = db["ai_results"].find(
            {"history_id": hid},
            {"raw_id": 1, "url": 1}
        )
        batch_raw_ids = []
        batch_urls = []
        for d in cursor:
            rid = d.get("raw_id")
            if isinstance(rid, ObjectId):
                batch_raw_ids.append(rid)
            u = (d.get("url") or "").strip()
            if u:
                batch_urls.append(u)

        candidates_raw_ids.update(batch_raw_ids)
        candidates_urls.update(batch_urls)

        print(f"- {h.get('subject','(no subject)')} ({h['created_at'].astimezone(timezone.utc).strftime('%Y-%m-%d')}): "
              f"{len(batch_raw_ids)} raw_id refs, {len(batch_urls)} url refs")

    if not candidates_raw_ids and not candidates_urls:
        print("No raw_insights candidates referenced by eligible histories.")
        return

    # 3) determine which candidates are still referenced by other histories
    #    A) raw_id-based check
    still_referenced_raw_ids: Set[ObjectId] = set()
    if candidates_raw_ids:
        # any ai_results that reference these raw_ids but NOT in the eligible history set?
        other_refs = db["ai_results"].find(
            {
                "raw_id": {"$in": list(candidates_raw_ids)},
                "history_id": {"$nin": list(eligible_hids)}
            },
            {"raw_id": 1}
        )
        for r in other_refs:
            rid = r.get("raw_id")
            if isinstance(rid, ObjectId):
                still_referenced_raw_ids.add(rid)

    #    B) url-based check (for any ai_results that didn't have raw_id filled)
    still_referenced_urls: Set[str] = set()
    if candidates_urls:
        other_url_refs = db["ai_results"].find(
            {
                "url": {"$in": list(candidates_urls)},
                "history_id": {"$nin": list(eligible_hids)}
            },
            {"url": 1}
        )
        for r in other_url_refs:
            u = (r.get("url") or "").strip()
            if u:
                still_referenced_urls.add(u)

    # 4) build deletable sets: those NOT referenced elsewhere
    deletable_raw_ids = candidates_raw_ids - still_referenced_raw_ids
    # For URL-based, map to raw_insights by url (only those not referenced elsewhere)
    deletable_urls = candidates_urls - still_referenced_urls

    # Resolve urls → raw_insights._id to delete by _id when possible
    url_to_raw_ids: Dict[str, ObjectId] = {}
    if deletable_urls:
        for doc in db["raw_insights"].find({"url": {"$in": list(deletable_urls)}}, {"_id": 1, "url": 1}):
            u = (doc.get("url") or "").strip()
            if u:
                url_to_raw_ids[u] = doc["_id"]

    # merge url-resolved ids into final deletable set
    final_deletable_raw_ids: Set[ObjectId] = set(deletable_raw_ids)
    final_deletable_raw_ids.update(url_to_raw_ids.values())

    print(f"Candidates (raw_ids): {len(candidates_raw_ids)} | still referenced: {len(still_referenced_raw_ids)} | "
          f"deletable by raw_id: {len(deletable_raw_ids)}")
    print(f"Candidates (urls): {len(candidates_urls)} | still referenced: {len(still_referenced_urls)} | "
          f"deletable resolved to raw_ids: {len(url_to_raw_ids)}")
    print(f"TOTAL raw_insights docs deletable: {len(final_deletable_raw_ids)}")

    if dry_run:
        # show a small preview of what would be deleted
        preview_ids = list(final_deletable_raw_ids)[:20]
        if preview_ids:
            preview_docs = list(db["raw_insights"].find({"_id": {"$in": preview_ids}}, {"_id": 1, "url": 1, "title": 1}))
            print("Dry run preview (up to 20 docs):")
            for d in preview_docs:
                print(f"  - {_short_id(d['_id'])} | {d.get('title','(no title)')} | {d.get('url','')}")
        print("Dry run mode: no deletions performed. Pass dry_run=False to execute.")
        return

    # 5) perform deletion
    deleted_count = 0
    if final_deletable_raw_ids:
        res = db["raw_insights"].delete_many({"_id": {"$in": list(final_deletable_raw_ids)}})
        deleted_count = getattr(res, "deleted_count", 0)

    print(f"Cleanup complete. Deleted {deleted_count} raw_insights docs.")


def _short_id(oid: ObjectId) -> str:
    s = str(oid)
    return s[:6] + "…" + s[-4:]