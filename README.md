# raspberry
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/feedly_backup.yml/badge.svg)

![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/telegram_notify.yml/badge.svg)

<!-- Deprecated: GitHub billing API endpoints have been deprecated -->
<!-- ![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/github_quotas.yml/badge.svg) -->

![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/imdb_backup.yml/badge.svg)

![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/raspberry_outage.yml/badge.svg)


Deployment is configured via tailscale/github-action, CI will have access to the Tailscale network. Need to include the action and provide it an ephemeral authentication key (90 days). (A regular authentication key will also work, but then you have to do all that removing-nodes business.)
