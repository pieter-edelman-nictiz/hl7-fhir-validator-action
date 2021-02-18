#!/usr/bin/env python3

import sys, yaml
import xml.etree.ElementTree as ET
from optparse import OptionParser, OptionValueError

issue_levels = {
    "fatal": 0,
    "error": 1,
    "warning": 2,
    "information": 3
}

class Result:
    def __init__(self, file_path):
        self.file_path = file_path

        # Get the id of the resource, if any
        resource_tree = ET.parse(file_path)
        try:
            self.id = resource_tree.find(".//f:id", ns).attrib["value"]
        except AttributeError:
            self.id = None

        self.issues = []

    def addIssue(self, line, col, severity, text, expression):
        if not severity in issue_levels:
            raise Exception(f"Unknown severity '{severity}' when validating file {self.file_path}")
        self.issues.append({
            "line": line,
            "col": col,
            "severity": severity,
            "text": text,
            "expression": expression
        })

if __name__ == "__main__":
    parser = OptionParser("usage: %prog [options] validator_result.xml")
    parser.add_option("-a", "--fail-at", type = "choice", choices = ["error", "warning", "information"], default = "error", 
        help="The level at which issues are considered fatal (error, warning or information). If issues at this level or more grave occur, this script will exit with a non-zero status.")
    parser.add_option("-v", "--verbosity-level", type = "choice", choices = ["error", "warning", "information"], default = "information",
        help="Only show issues at this level or lower (fatal, error, warning, information).")
    parser.add_option("--ignored-issues", type="string",
        help="A YAML file with issues that should be ignored.")

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("Exactly one argument expected")

    fail_level      = issue_levels[options.fail_at]
    verbosity_level = issue_levels[options.verbosity_level]
    if fail_level > verbosity_level:
        parser.error("Chosen verbosity level would silence fatal issues")   

    ignored_issues = {}

    if options.ignored_issues:
        with open(options.ignored_issues, "r") as f:
            ignored_issues = yaml.safe_load(f)
        if type(ignored_issues) != dict: # Empty file
            ignored_issues = {}

    tree = ET.parse(args[0])
    ns = {"f": "http://hl7.org/fhir"}

    # Parse the Validator output, which will produce an OperationOutcome for each checked file (either a singele
    # OperationOutcome or a Bundle)
    results = []
    if tree.getroot().tag == "{http://hl7.org/fhir}OperationOutcome":
        outcomes = [tree.getroot()]
    else:
        outcomes = tree.getroot().findall(".//f:OperationOutcome", ns)
   
    for outcome in outcomes:
        file_name = outcome.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-file']/f:valueString", ns).attrib["value"]
        result = Result(file_name)

        curr_ignored_issues = {}
        if result.id in ignored_issues and "ignored issues" in ignored_issues[result.id]:
            curr_ignored_issues = ignored_issues[result.id]["ignored issues"]

        for issue in outcome.findall("f:issue", ns):
            # Extract relevant information from the OperationOutcome
            try:
                text = issue.find("f:details/f:text", ns).attrib["value"]
            except AttributeError:
                text = "_No description_"

            try:
                line = issue.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-issue-line']/f:valueInteger", ns).attrib["value"]
                col  = issue.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-issue-col']/f:valueInteger", ns).attrib["value"]
            except AttributeError:
                line = "?"
                col  = "?"

            severity = issue.find("f:severity", ns).attrib["value"]

            try:
                expression = issue.find("f:expression", ns).attrib["value"]
            except AttributeError:
                expression = ""

            # Check to see if the issue is known and should be ignored
            issue_ignored = False
            if expression in curr_ignored_issues:
                for known_issue in curr_ignored_issues[expression]:
                    if "message" in known_issue:
                        if text.startswith(known_issue["message"]):
                            if "reason" not in known_issue:
                                print(f"Issue at {result.id}/{expression} ignored without providing a reason")
                                sys.exit(1)
                            issue_ignored = True
                            known_issue["processed"] = True
            # When everything is ok, the Validator will output an "All OK" issue which we should ignore.
            elif severity == "information" and text == "All OK" and len(outcome.findall("f:issue", ns)) == 1:
                issue_ignored = True

            if not issue_ignored:
                result.addIssue(line, col, severity, text, expression)
        results.append(result)

        # Check if all issues have been processed
        for expression in curr_ignored_issues:
            for known_issue in curr_ignored_issues[expression]:
                if "processed" not in known_issue:
                    print(f"An ignored issue was provided for {result.id}/{expression}, but the issue didn't occur")
                    sys.exit(1)

    # Print out the results per file
    success = True
    for result in results:
        if len(result.issues) > 0:
            id_str = "== " + result.file_path
            if result.id:
                id_str += f" ({result.id})"
            print(id_str)
            for issue in result.issues:
                if issue_levels[issue["severity"]] <= fail_level:
                    success = False
                if issue_levels[issue["severity"]] <= verbosity_level:
                    print(f"  -  {issue['severity']} at {issue['expression']} ({issue['line']}, {issue['col']}):")
                    print(f"     {issue['text']}")
            print()

    if not success:
        print("There were errors during validation")
        sys.exit(1)
    print("All well")
