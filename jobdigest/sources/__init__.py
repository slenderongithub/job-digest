"""Source scrapers. Each module exposes a Scraper subclass of SourceScraper that
returns a list[JobListing]. The orchestrator picks which to run from the
`enabled_sources` list in profile.yaml."""
