#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET
from optparse import OptionParser, OptionValueError

issue_levels = {
    "error": 0,
    "warning": 1,
    "information": 2
}

class Result:
    def __init__(self, file_path):
        self.file_path = file_path

        self.issues = []

    def addIssue(self, line, col, severity, text):
        if not severity in issue_levels:
            raise Exception(f"Unknown severity '{severity}' when validating file {self.file_path}")
        self.issues.append({
            "line": line,
            "col": col,
            "severity": severity,
            "text": text
        })

if __name__ == "__main__":
    parser = OptionParser("usage: %prog [options] validator_result.xml")
    parser.add_option("-a", "--fail-at", type = "choice", choices = ["error", "warning", "information"], default = "error", 
        help="The level at which issues are considered fatal (error, warning or information). If issues at this level or more grave occur, this script will exit with a non-zero status.")
    parser.add_option("-v", "--verbosity-level", type = "choice", choices = ["error", "warning", "information"], default = "information",
        help="Only show issues at this level or lower (0 = error, 1 = warning, 2 = information).")
    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("Exactly one argument expected")

    fail_level      = issue_levels[options.fail_at]
    verbosity_level = issue_levels[options.verbosity_level]
    if fail_level > verbosity_level:
        parser.error("Chosen verbosity level would silence fatal issues")   

    tree = ET.parse(args[0])
    ns = {"f": "http://hl7.org/fhir"}

    results = []
    if tree.getroot().tag == "{http://hl7.org/fhir}OperationOutcome":
        outcomes = [tree.getroot()]
    else:
        outcomes = tree.getroot().findall(".//f:OperationOutcome", ns)
    for outcome in outcomes:
        file_name = outcome.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-file']/f:valueString", ns).attrib["value"]
        result = Result(file_name)

        for issue in outcome.findall("f:issue", ns):
            line     = issue.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-issue-line']/f:valueInteger", ns).attrib["value"]
            col      = issue.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-issue-col']/f:valueInteger", ns).attrib["value"]
            severity = issue.find("f:severity", ns).attrib["value"]
            text     = issue.find("f:details/f:text", ns).attrib["value"]
            result.addIssue(line, col, severity, text)
        results.append(result)

    success = True
    for result in results:
        if len(result.issues) > 0:
            print(f"== {result.file_path}")
            for issue in result.issues:
                if issue_levels[issue["severity"]] <= fail_level:
                    success = False
                if issue_levels[issue["severity"]] <= verbosity_level:
                    print(f"  -  {issue['severity']} ({issue['line']}, {issue['col']}):")
                    print(f"     {issue['text']}")
            print()

    if not success:
        print("There were errors during validation")
        sys.exit(1)
    print("All well")
