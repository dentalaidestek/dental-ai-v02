# Profile hub simplification

Profilim is the common entry for personal information, professional status/documents and the expert profile. The menu uses Profilim consistently, and the expert shortcut keeps a stable label while retaining its status icon. The bottom Profile tab stays selected in the expert editor.

Personal information contains the photo, name and contact editors. The expert editor links back to these shared editors when a photo already exists; first-time applications can still add their required photo without leaving the form. Duplicate read-only identity fields were removed. University and specialty remain available under professional information.

Professional information summarizes membership, expert and pending title-change verification. Experts are not prompted to send an additional generic membership document; independently submitted membership applications still show their actual state. Expert profile management and the published self-profile are reachable from Profilim.

`/account/documents?purpose=membership|expert|title` uses one document wizard. Fixed expert/title document types are preselected and open directly at upload. Membership documents retain four selectable types and their 5 MiB limit; expert/title documents retain their 10 MiB limit. Existing membership and title URLs remain compatible. The obsolete title-specific template was removed.

Membership and title submissions return to the open professional/documents section. Expert document replacements also return there, preserve profile content and prices, and trigger the existing submitted/pending/passive review state. Replacements are blocked while expert review is pending; PostgreSQL owner/profile locks serialize simultaneous replacements, and the admin review locks the profile too. This UI unification never automatically transfers membership approval to expert eligibility. Title-change submissions continue to preserve the currently approved expert identity and availability.

No schema migration, new AI calls, main-branch changes or production deployment were needed. Seven profile workflow tests cover shared navigation, first applications, approved/pending experts, document replacement, title replacement and access/error handling. PostgreSQL CI adds a simultaneous expert-document replacement scenario. Frontend controls were checked with a Node harness; actual browser visual QA remains unavailable in this environment because Chromium download failed earlier.
