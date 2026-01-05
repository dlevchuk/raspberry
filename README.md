# raspberry

Raspberry Pi infrastructure management repository with automated backups, monitoring, and deployment via GitHub Actions and Ansible.

## Workflow Status

![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/feedly_backup.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/telegram_notify.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/imdb_backup.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/raspberry_outage.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/goodreads_backup.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/meteo.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/power.yml/badge.svg)
![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/ansible.yml/badge.svg)



<!-- Deprecated: GitHub billing API endpoints have been deprecated -->
<!-- ![workflow](https://github.com/dlevchuk/raspberry/actions/workflows/github_quotas.yml/badge.svg) -->

## Overview

This repository manages a Raspberry Pi home server infrastructure with:

- **Automated Backups**: Feedly, IMDb, Goodreads, and Notion data backups
- **Monitoring**: Power outage alerts, weather reports, and internet connectivity monitoring
- **Infrastructure as Code**: Ansible playbooks for automated server configuration
- **CI/CD**: GitHub Actions workflows for automated deployment and scheduled tasks
- **Docker Applications**: Automated deployment of containerized services

## Project Structure

```
raspberry/
├── ansible/              # Ansible playbooks for infrastructure management
│   ├── roles/
│   │   ├── common/      # Common system setup (watchdog, kernel panic config, etc.)
│   │   └── docker_apps/ # Docker application deployments
│   └── site.yml         # Main playbook
├── scripts/             # Python scripts for various tasks
│   ├── backup_feedly/   # Feedly RSS backup
│   ├── backup_goodreads_web/  # Goodreads books backup (see README)
│   ├── backup_imdb/     # IMDb lists and ratings backup
│   ├── backup_notion/   # Notion workspace backup
│   ├── github_quotas/   # GitHub API quota monitoring (deprecated)
│   ├── light_outage/    # Power outage monitoring and alerts
│   ├── meteo_data/      # Weather data collection
│   └── raspberry_outage/ # Internet connectivity monitoring
└── .github/workflows/   # GitHub Actions workflows
    ├── ansible.yml      # Ansible deployment automation
    ├── feedly_backup.yml
    ├── goodreads_backup.yml
    ├── imdb_backup.yml
    ├── meteo.yml        # Weather reports
    ├── power.yml        # Power outage alerts
    ├── raspberry_outage.yml
    └── telegram_notify.yml  # Failure notifications
```

## Features

### Backup Scripts

- **Goodreads Backup**: Automated weekly backup of reading lists (read, currently-reading, to-read) - see [scripts/backup_goodreads_web/README.md](scripts/backup_goodreads_web/README.md)
- **Feedly Backup**: RSS feed backup script
- **IMDb Backup**: Backup of watchlists and ratings
- **Notion Backup**: Workspace backup script

### Monitoring & Alerts

- **Power Outage Monitoring**: Tracks scheduled power outages and sends Telegram alerts
- **Weather Reports**: Automated weather data collection and reporting
- **Internet Connectivity**: Monitors Raspberry Pi internet connection and alerts on outages
- **Telegram Notifications**: Automatic failure notifications for all workflows

### Infrastructure Management

- **Ansible Playbooks**: Automated server configuration and Docker app deployment
- **Watchdog Setup**: Hardware watchdog configuration for automatic reboot on system hangs
- **Cron Management**: Automated cron job setup for scheduled tasks

## Deployment

Deployment is configured via `tailscale/github-action`, providing CI access to the Tailscale network. The setup requires:

- **Ephemeral Authentication Key** (90 days recommended) - stored as `TAILSCALE_AUTHKEY` secret
- **OAuth Credentials** (for Ansible workflow) - `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET`

A regular authentication key will also work, but requires manual node removal management.

### Required GitHub Secrets

See [.github/workflows/README.md](.github/workflows/README.md) for a complete list of required secrets.

## Getting Started

1. Clone the repository
2. Configure GitHub Secrets in repository settings
3. Push changes to trigger deployment workflows
4. Scheduled workflows will run automatically


Deployment is configured via tailscale/github-action, CI will have access to the Tailscale network. Need to include the action and provide it an ephemeral authentication key (90 days). (A regular authentication key will also work, but then you have to do all that removing-nodes business.)
