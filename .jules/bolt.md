## 2026-02-19 - Caching Role Checks
**Learning:** In Django applications with heavy RBAC, redundant permission checks can lead to multiple database hits per request. Caching group names on the user instance for the duration of the request can measurably reduce query count.
**Action:** Always check if a request performs multiple `user.groups.filter(...)` calls and introduce a simple in-memory cache on the user object.
**Impact:** Reduced redundant queries for role checks in views from O(R) to O(1) where R is the number of checks per request.
