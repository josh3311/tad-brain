# AI Invoice Chaser — Architecture Plan
Generated: 2026-06-27T23:01:03.374697

## MVP Scope
Read a CSV of unpaid invoices and generate 3 personalized, human-sounding follow-up email drafts per invoice with escalating urgency. User selects which emails to send via CLI menu.

## Target User
Small contractor, 1-5 employees

## Files

### main.py
CLI tool that takes unpaid invoice data and generates personalized follow-up email drafts with human-sounding language templates.

### invoice_processor.py
Parses invoice CSVs (client name, amount, days overdue) and formats data for email generation.

## Data Model
Invoice object with fields: client_name, amount, days_overdue, last_invoice_date. Email draft with fields: subject, body, personalization_level. CSV input format: client_name,invoice_amount,days_overdue.

## Done Criteria
User can upload CSV, see 3 email options per invoice, select emails to copy/send, and run end-to-end in under 2 minutes. No auth, no database, no integrations.