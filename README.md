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

Additionally, these parameters can be used to control the automation process:

* fail-at: The level at which issues are considered fatal (error, warning or information). If issues at this level or more grave occur, this action will fail.
* verbosity-level: Only show issues at this level or more severe (error, warning or information).
* ignored-issues: An optional YAML file with issues to ignore. See below for more information.

## Suppressing messages

Using the "ignored issues" key, it is possible to pass one or more YAML files that describe issues that should be suppressed. The file should be formatted in the following way:
  
  ```yaml
  [resource]:
    ignored issues:
      [location]:
        - message: "[The error message (may be just the first part)]"
          reason: "[An explanation of why the issue can be ignored]"
        - message: "[Another error to ignore]"
          reason: "[Another explanation]"
  ```

Where:
* `[resource]` may either be the `Resource.id` or the relative path to the file.
* `[location]` may be either the FHIRPath expression _as reported by the Validator_ or the id of the element where the issue occurs. Asterisk may be used as wildcards on the location.

The "reason" key is mandatory.

By default, it is required that each of the described issues actually occurs during validation (only for the resources actually being validated, that is). If not, an error is generated. This behavior can be suppressed by including the key `issues should occur` set to _false_ in the YAML file (or the document when it is a multi-document YAML file). Only in this situation, wildcards can be used on the resource.id as well.

The rationale for this is that you can document different kinds of errors in different files; for example one file for all issues that are the result of design choices, and another file to suppress more ephemeral errors, like a terminlogy server not supporting certain code systems.