# Accessibility and UI Regression

LiveFireTTX v1.4 adds a browser-driven baseline for facilitator, evaluator, and
participant workflows. The interface declares English document language,
provides a keyboard skip link, uses visible focus indicators, and honors the
reduced-motion preference.

## Automated Browser Coverage

`make e2e` starts an isolated local application and uses Chromium to:

- Navigate the home and guided setup experiences
- Create a real generated exercise through the browser
- Open command-center, run, evaluator, and participant views
- Create a signed evidence export and confirm retained verification status
- Repeat critical views at desktop and 390-pixel mobile widths
- Fail on browser console or page exceptions
- Capture screenshots for every checked view

The accessibility audit checks document language, main landmarks, one top-level
heading, unique IDs, form labels, image alternatives, named controls, heading
order, skip-link keyboard behavior, and horizontal overflow. It is a regression
baseline, not a certification or a substitute for assistive-technology testing.

## Local Use

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
make e2e
```

Screenshots and server logs are written to `.e2e-artifacts/`, which is ignored
by Git. GitHub Actions uploads that directory when the browser job fails.

Release review should still include keyboard-only operation, zoom at 200%, and
a screen-reader pass through guided setup, facilitator run mode, evaluator
workspace, and participant display.
