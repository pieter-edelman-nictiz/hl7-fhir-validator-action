# FHIR validator

This action runs the [HL7 FHIR Validator](https://confluence.hl7.org/display/FHIR/Using+the+FHIR+Validator) in your Github workflow, allowing you to continuously test your materials. You can configure the gravity of issues at which the test should fail.

Note: this project is in no way affiliated with HL7 or the FHIR Validator.

## Basic usage

In your workflow YAML, add the following step:

```yaml
- name: Run the validator against the profiles
  uses: pieter-edelman-nictiz/hl7-validator-action@master
  with:
    source: path/to/sources/to/validate
    ...
```

It might be a good idea to keep the re-use the validator cache across runs using the [cache action](https://github.com/actions/cache) (there's usually no need to cache the FHIR Validator .jar itself as it is already hosted on Github, but if you want to, the validator will be downloaded to the `~/validator` folder). A minimal example might look like:

```yaml
name: Check FHIR messages
on: pull_request

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2
      - name: Restore validator cache
        uses: actions/cache@v2
        with:
          path: ~/.fhir/packages
          key: fhir-cache
      - name: Run the validator against the FHIR messages
        uses: pieter-edelman-nictiz/hl7-validator-action@master
        with:
          version: "4.0"
          ig: resources/
          recurse: true
          source: messages/*
```

## Parameters

This action supports a subset of the FHIR Validator parameters. Their usage is exactly the same, so please refer to [the official documentation](https://confluence.hl7.org/display/FHIR/Using+the+FHIR+Validator) for more information.

* **source**: a file, url, directory or pattern for resources to validate. This is the only required parameter.
* version: The FHIR version to use.
* ig: An IG or profile definition to load.
* recurse: Look in subfolders when "ig" refers to a folder.
* tx: The [base] url of a FHIR terminology server.
* profile: the canonical URL to validate against.
* language: The language to use when validating coding displays - same value as for xml:lang.

Additionally, two parameters are control to steer the automation process:

* allow-level: The level from which issues are considered not fatal (0 = error, 1 = warning, 2 = information). If issues below the specified level occur, this action will fail.
* verbosity-level: Only show issues at this level or lower (0 = error, 1 = warning, 2 = information).
