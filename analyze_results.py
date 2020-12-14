#!/usr/bin/env python3

import sys
import xml.etree.ElementTree as ET

levels = {
    "error": 0,
    "warning": 1,
    "information": 2
}

class Result:
    def __init__(self, file_path):
        self.file_path = file_path

        self.issues = []

    def addIssue(self, line, col, severity, text):
        if severity not in ["error", "warning", "information"]:
            raise Exception(f"Unknown severity '{severity}' when validating file {self.file_path}")
        self.issues.append({
            "line": line,
            "col": col,
            "severity": severity,
            "text": text
        })

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage {sys.argv[0]} validator_output.xml [allow_level]")
        print("Where allow_level is a number from 0-2 to indicate at which level errors are still allowed (0=error, 1=warning, 2=information)")
        sys.exit(1)

    if len(sys.argv) == 3:
        allow_level = int(sys.argv[2])
    else:
        allow_level = 1

    tree = ET.parse(sys.argv[1])
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
                if levels[issue["severity"]] < allow_level:
                    success = False
                print(f"  -  {issue['severity']} ({issue['line']}, {issue['col']}):")
                print(f"     {issue['text']}")
            print()

    if not success:
        print("There were errors during validation")
        sys.exit(1)
    print("All well")
