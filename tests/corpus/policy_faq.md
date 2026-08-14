# Data Retention Policy

This policy explains how long we keep different categories of data and what
happens when an account is closed. It applies to all customers on the Pro,
Team, and Enterprise plans. It does not apply to data processed under a
custom Data Processing Addendum (DPA), which takes precedence where the two
conflict.

## Summary

> If you only read one section, read this one. Everything below expands on
> these three points.
>
> 1. Active account data is kept for as long as the account is active.
> 2. After account closure, data is retained for 30 days, then permanently
>    deleted.
> 3. Backups are retained separately for up to 90 days for disaster
>    recovery, and are not accessible through the normal product.

## What counts as "data"

We distinguish between a few categories:

- **Content data** — anything you or your team explicitly created, e.g.
  documents, messages, uploaded files.
- **Usage data** — logs of feature usage, e.g. which pages were viewed and
  when.
- **Billing data** — invoices, payment method metadata (never full card
  numbers), and subscription history.
- **Support data** — the contents of support tickets and any attachments.

Each category has a different retention schedule, described below.

## Retention schedule

| Data category | While account is active | After closure | Backup retention |
|:---|:---:|:---:|:---:|
| Content data | Indefinite | 30 days | +90 days |
| Usage data | 13 months | 30 days | +90 days |
| Billing data | 7 years (legal requirement) | 7 years | N/A |
| Support data | 24 months | 30 days | +90 days |

Billing data is retained for 7 years regardless of account status because
several jurisdictions we operate in (e.g. the U.S., the U.K., and members of
the E.U.) require it for tax and audit purposes. This is not configurable.

## Frequently asked questions

### Can I request deletion before the 30-day window ends?

Yes. Contact support and ask for immediate deletion. Note that this is
irreversible: once processed, we cannot restore the account even if you
change your mind the next day. Immediate deletion still does not affect
billing data, which follows the 7-year schedule described above.

### Does deleting a workspace delete data for all members?

Yes, deleting a workspace deletes content data, usage data, and support
data for every member of that workspace, following the same 30-day and
90-day schedule as account closure. Individual members do not retain
copies unless they exported their own data beforehand.

### What about data shared with third-party integrations?

Once data leaves our systems through an integration you configured (e.g.
Slack, Google Drive, or a custom webhook), it is subject to that third
party's own retention policy, not ours. We recommend reviewing the
retention policy of any integration before enabling it, particularly for
regulated data.

### I'm a Enterprise customer with a custom DPA. Which policy applies?

Your DPA. If your DPA specifies different retention periods than this
document, the DPA governs. Contact your account manager if you are unsure
which terms apply to your account.

## Requesting your data before closure

Before closing an account, you can export:

1. All content data as a zip archive
2. Usage data for the trailing 13 months as CSV
3. Support ticket history as PDF

To request an export:

1. Go to Settings > Data Export
2. Select the categories you want
3. Click "Request export"
4. You will receive a download link by email within 24 hours
   - the link expires after 7 days
   - re-request if it expires before you download it

## Changes to this policy

We may update this policy from time to time. Material changes (e.g.
shortening a retention period) will be communicated by email at least 30
days in advance. Non-material changes, such as clarifying existing
language, may be made without prior notice.
