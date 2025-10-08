# 🚨 CALENDAR CRITICAL BUG - COMPLETE DIAGNOSIS

## EXECUTIVE SUMMARY

**Status:** ✅ Athena milestone DOES pass filters  
**Problem:** ❌ Date range doesn't update when navigating to previous months  
**Impact:** September/August calendars are empty even though milestones exist

---

## 1. EXACT QUERYSET

```python
# Line 743-745: core/views.py
contracts = Contract.objects.filter(
    status__in=['completed', 'needs_clarification', 'processing']
).select_related('payment_terms')
```

**Result:** 68 contracts found  
**SQL:** `WHERE status IN ('completed', 'needs_clarification', 'processing')`

---

## 2. DATE RANGE VARIABLES (Current State)

```
today = 2025-10-07
start_date = today.replace(day=1) = 2025-10-01
end_date = today + timedelta(30) = 2025-11-06

cal_month = 10 (October)
cal_year = 2025
```

**Problem:** Date range is FIXED based on today, doesn't adjust for month navigation

---

## 3. MILESTONE FILTERING - Athena Finance

```
Contract: Athena Finance (ID: 451)
Status: completed

Milestone ID: 373 "Compliance Controls"
  invoice_date: 2025-09-15
  due_date: 2025-10-06
  date_to_check: 2025-10-06
  
  FILTER: 2025-10-01 <= 2025-10-06 <= 2025-11-06
  RESULT: ✅ PASSES
```

**✅ CONCLUSION:** Athena milestone DOES pass the date filter!

---

## 4. CALENDAR MONTH FILTER (Line 835)

```python
# This filter ONLY displays milestones in the viewed month
for invoice in timeline_invoices:
    if invoice['date'].month == cal_month and invoice['date'].year == cal_year:
        invoices_by_date[invoice['date'].day].append(invoice)
```

**Athena Test:**
```
Invoice date: 2025-10-06
  invoice['date'].month (10) == cal_month (10): True ✅
  invoice['date'].year (2025) == cal_year (2025): True ✅
  PASSES: True ✅
  → Added to calendar day 6
```

**✅ CONCLUSION:** Athena milestone DOES pass calendar month filter!

---

## 5. WHY PREVIOUS MONTHS ARE EMPTY

### The Critical Bug:

**Scenario:** User clicks ← to navigate to September 2025

```python
# User action sets cal_month_param
cal_month_param = '2025-09'  # From URL ?cal_month=2025-09
cal_month = 9  # September
cal_year = 2025

# BUT date range calculation happens BEFORE this
# Lines 723-736 run first, using today
start_date = today.replace(day=1)  # Oct 1 (WRONG for September!)
end_date = today + timedelta(30)   # Nov 6

# Result:
# - Date range: Oct 1 - Nov 6
# - Calendar displays: September
# - September milestones (all dates < Oct 1) are EXCLUDED
```

**Database has 10 milestones in September 2025**  
**All are filtered out because Sept < Oct 1**

---

## 6. TEMPLATE VARIABLES (Lines 859-871)

```python
context = {
    'active_tab': active_tab,
    'upcoming_payments': upcoming_payments,
    'timeline_invoices': timeline_invoices,        # All invoices in date range
    'timeline_by_client': dict(timeline_by_client),
    'timeline_months': timeline_months,
    'calendar_days': calendar_days,                # Calendar grid with invoices
    'calendar_month': datetime(cal_year, cal_month, 1).date(),
    'total_monthly': total_monthly,
    'payments_count': payments_count,
    'average_invoice': average_invoice,
    'sort_by': sort_by,
    'sort_order': sort_order,
}
```

---

## 7. ROOT CAUSE ANALYSIS

### Current Flow (BROKEN):

```
1. User clicks ← to September
   → URL: /forecast/?tab=calendar&cal_month=2025-09

2. forecast_view() executes:
   Line 713: today = 2025-10-07
   Line 735: start_date = 2025-10-01  ← IGNORES cal_month!
   Line 736: end_date = 2025-11-06
   
3. Line 751-754: Fetch milestones
   → Only fetches Oct 1 - Nov 6 milestones
   → September milestones NEVER queried
   
4. Line 823-830: Set cal_month = 9
   → Too late! Data already filtered
   
5. Line 835: Filter for September
   → No September data because it was excluded earlier
   
6. Result: Empty calendar
```

---

## 8. THE FIX

### Option A: Adjust date range based on cal_month (RECOMMENDED)

**Change Lines 722-736:**

```python
# BEFORE:
if custom_start and custom_end:
    start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
    end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
else:
    # Default logic for preset ranges
    days = request.GET.get('days', '30')
    if days == 'custom':
        start_date = today - timedelta(days=365)
        end_date = today + timedelta(days=365)
    else:
        try:
            days_int = int(days) if days != 'all' else 365
        except ValueError:
            days_int = 30
        start_date = today.replace(day=1)
        end_date = today + timedelta(days=days_int)

# AFTER:
# Check if user is navigating to specific calendar month
cal_month_param = request.GET.get('cal_month')
if cal_month_param:
    # User navigated to specific month - adjust date range
    cal_date = datetime.strptime(cal_month_param, '%Y-%m').date()
    # Fetch data for that entire month
    start_date = cal_date.replace(day=1)
    # End date = last day of that month
    if cal_date.month == 12:
        end_date = cal_date.replace(year=cal_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = cal_date.replace(month=cal_date.month + 1, day=1) - timedelta(days=1)
elif custom_start and custom_end:
    start_date = datetime.strptime(custom_start, '%Y-%m-%d').date()
    end_date = datetime.strptime(custom_end, '%Y-%m-%d').date()
else:
    # Default logic for preset ranges
    days = request.GET.get('days', '30')
    if days == 'custom':
        start_date = today - timedelta(days=365)
        end_date = today + timedelta(days=365)
    else:
        try:
            days_int = int(days) if days != 'all' else 365
        except ValueError:
            days_int = 30
        start_date = today.replace(day=1)
        end_date = today + timedelta(days=days_int)
```

### Option B: Remove month filter (NOT RECOMMENDED)

This would show all milestones from date range on every calendar page.

---

## 9. DEBUG LOGGING TO ADD

```python
# Line 735 - After date calculation
import logging
logger = logging.getLogger(__name__)

logger.info(f"FORECAST VIEW: today={today}, start_date={start_date}, end_date={end_date}")
logger.info(f"FORECAST VIEW: cal_month={cal_month}, cal_year={cal_year}")

# Line 754 - After generating invoices
logger.info(f"FORECAST VIEW: Generated {len(timeline_invoices)} timeline invoices")

# Line 691 - In generate_invoice_schedule, inside loop
logger.info(f"MILESTONE: contract={contract.id}, milestone={milestone.id}, "
           f"due_date={milestone.due_date}, passes={in_range}")

# Line 836 - After calendar month filter
logger.info(f"CALENDAR: {len(invoices_by_date)} days with invoices in month {cal_month}")
```

---

## 10. RECOMMENDATION

**✅ OPTION A - Adjust date range based on cal_month**

**Why:**
1. Allows month navigation to work properly
2. Fetches only needed data for viewed month
3. Efficient - doesn't query unnecessary months
4. Maintains existing "Next 30 days" behavior for default view

**Implementation:**
- Add cal_month_param check at beginning of date calculation
- Calculate start/end dates for that specific month
- Keep existing logic for default view

---

## VERIFICATION

After fix, test:
1. Default view: Should show Oct 1 - Nov 6 ✅
2. Navigate to September: Should show Sept 1-30 ✅
3. Navigate to November: Should show Nov 1-30 ✅
4. Athena milestone: Should appear on Oct 6 ✅



