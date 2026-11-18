# Security boundaries

- One local instance has one audience and sensitivity level. Use a separate owner-only root and, where different people or service accounts need access, separate OS identities. Use a trusted local filesystem. The core checks NTFS ACLs or the POSIX owner and 0700 root. Disk encryption and transport are deployment responsibilities.
- Authorize each source before import. Only the selected manifest paths or export file are in scope. Raw archive import and raw reads require separate authorization. Project handoff contains structured checkpoints and references. The recipient needs separately granted file access.
- Keep data, credentials and production logs outside the repository. Use synthetic fixtures for issues, tests and reproductions. Report suspected exposure privately to the owner of your instance.
- Shared release artifacts are produced from the standalone source tree. Check the Git root, history scan, CI results and SHA-256 manifest before publishing or installing a release.
