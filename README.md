### Field Sales

Offline-first field sales client and Frappe backend for NASECO.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site <site> install-app fieldsales
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/fieldsales
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Local document protection

Keep architecture and design materials in the mobile workspace or another local directory.
Enable the repository's pre-push hook after cloning:

```bash
git config --local core.hooksPath .githooks
```

The hook checks outgoing commits, including files removed by a later outgoing commit.
The ignore rules keep these files out of normal staging.

### License

mit
