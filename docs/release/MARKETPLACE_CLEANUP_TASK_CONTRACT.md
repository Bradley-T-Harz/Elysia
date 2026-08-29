# Marketplace Cleanup Task Contract

Status: separate future website task; not executed by Pass 7.

Pass 7 does not authorize website source mutation, Supabase mutation, listing
deletion, or Marketplace publication.

The cleanup pass must first determine the source of every candidate listing:

- If entries are static source content, inspect the website repository and prepare a
  scoped source diff with layout and empty-state tests.
- If entries are database/Supabase rows, export or inventory the exact row IDs and
  current public states without printing private data.
- Produce a dry-run hide/delete/deprecate plan naming only the intended records.
- Obtain release-owner/admin approval before any database mutation or destructive change.
- Do not mutate unrelated Marketplace records, tables, accounts, or assets.
- Preserve an honest empty state when no installable add-ons exist.
- Codev may be the first official draft/admin-only listing, but it cannot be marked
  installable until the Developer profile install path is real and verified.

Admin review means reviewed under the current process, not guaranteed safe. Website
cleanup and legal publication remain outside Elysia Core Pass 7.
