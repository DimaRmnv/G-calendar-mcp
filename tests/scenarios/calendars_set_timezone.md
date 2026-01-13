# Test Scenarios: calendars set_timezone

## Scenario 1: Set timezone with explicit account

**Request:**
```json
{
  "action": "set_timezone",
  "timezone": "Indian/Maldives",
  "account": "work"
}
```

**Expected:**
- Status: Success
- Response contains: `{"timezone": "Indian/Maldives", "updated": true}`

---

## Scenario 2: Set timezone without account (defaults to "work")

**Request:**
```json
{
  "action": "set_timezone",
  "timezone": "Europe/Kyiv"
}
```

**Expected:**
- Status: Success
- Uses "work" account by default
- Response contains: `{"timezone": "Europe/Kyiv", "updated": true}`

---

## Scenario 3: Set timezone for personal account

**Request:**
```json
{
  "action": "set_timezone",
  "timezone": "Asia/Bangkok",
  "account": "personal"
}
```

**Expected:**
- Status: Success
- Response contains: `{"timezone": "Asia/Bangkok", "updated": true}`

---

## Scenario 4: Invalid timezone

**Request:**
```json
{
  "action": "set_timezone",
  "timezone": "Invalid/Timezone",
  "account": "work"
}
```

**Expected:**
- Status: Error
- Error message from Google API about invalid timezone

---

## Scenario 5: Missing timezone parameter

**Request:**
```json
{
  "action": "set_timezone",
  "account": "work"
}
```

**Expected:**
- Status: Error
- Error: "timezone parameter required for 'set_timezone' action"

---

## Verification After Fix

Previous error:
```
Error calling tool 'calendars': 'Resource' object has no attribute 'patch'
```

This error should NO LONGER occur. The fix uses `calendars().patch()` instead of non-existent `settings().patch()`.
