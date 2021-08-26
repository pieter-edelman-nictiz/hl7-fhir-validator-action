#!/usr/bin/env python3

import json, os, sys, yaml
import xml.etree.ElementTree as ET
import xml.parsers.expat
from optparse import OptionParser, OptionValueError

issue_levels = {
    "fatal": 0,
    "error": 1,
    "warning": 2,
    "information": 3
}

class Formatter:
    """ Default provider for formatting characters """

    def __init__(self, is_github = False):
        self.is_github = is_github

    def __getattr__(self, value):
        return ""

class ColorFormatter(Formatter):
    """ Formatter to provide ANSI escape codes for terminal colors. """
    RESET       = "\033[0m"
    OK          = "\033[1;32m"
    ERROR       = "\033[1;31m"
    WARNING     = "\033[1;33m"
    INFORMATION = "\033[1;34m"

class Issue:
    def __init__(self, line, col, severity, text, expression):
        self.line       = line
        self.col        = col
        self.severity   = severity
        self.text       = text
        self.expression = expression
    
    def print(self, formatter, file_path):
        if self.severity in ["fatal", "error"]:
            color = formatter.ERROR
        elif self.severity == "warning":
            color = formatter.WARNING
        else:
            color = formatter.INFORMATION
        out =  f"  -  {color}{self.severity}{formatter.RESET} at {self.expression} ({self.line}, {self.col}):\n"
        out += f"     {self.text}"
        print(out)

        if (formatter.is_github):
            severity_command = "warning" if self.severity in ["warning", "information"] else "error"
            out = f"::{severity_command} file={os.getcwd()}/{file_path}"
            if self.line != "?":
                out += f",line={self.line}"
                if self.col != "?":
                    out += f",col={self.col}"
            out += f"::{self.text}"
            print(out)

class ElementId:
    """ Store element id's along with their line and column number. """

    def __init__(self, start, end, id):
        """ Store an element id. "start" and "end" should be tuples containing the line and column number of the 
            element with the specified id (inclusive). """
        self.start = (int(start[0]), int(start[1]))
        self.end   = (int(end[0]),   int(end[1]))
        self.id    = id
    
    def has(self, line, col):
        """ Check if the specified line and column are within the current element. Return the id on success or False
            when there's no match. """
        
        try:
            line = int(line)
            col  = int(col)
        except ValueError:
            # No valid line and/or column given
            return False

        if (line > self.start[0] or (line == self.start[0] and col >= self.start[1])) and \
           (line < self.end[0]   or (line == self.end[0]   and col <= self.end[1])):
           return self.id
        return False

class XMLElementIdMapper:
    """ Map all the elements with an id in an XML file. """

    def __init__(self):
        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler = self.start_handler
        self.parser.EndElementHandler   = self.end_handler

    def parse(self, path):
        """ Parse the file specified by path and return a list of ElementID instances for each element with an id. """
        self.elements = []
        self.element_ids = []
        self.parser.ParseFile(open(path, "rb"))
        return self.element_ids
 
    def start_handler(self, tag_name, attributes):
        curr_element = {
            "name": tag_name,
            "start": (self.parser.CurrentLineNumber, self.parser.CurrentColumnNumber)
        }
        if "id" in attributes:
            curr_element["id"] = attributes["id"]
        self.elements.append(curr_element)

    def end_handler(self, tag_name):
        curr_element = self.elements.pop()
        if "id" in curr_element:
            self.element_ids.append(ElementId(curr_element["start"], (self.parser.CurrentLineNumber, self.parser.CurrentColumnNumber), curr_element["id"]))

class JSONElementIdMapper(json.JSONDecoder):
    """ Map all the elements with an id in a JSON file.
        This is a bit of a kludge that works by intercepting the internal workings of the Python JSONDecoder.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parse_object = self.interceptingJSONObject
        self.scan_once = json.scanner.py_make_scanner(self)
    
    def parse(self, path):
        """ Parse the file specified by path and return a list of ElementID instances for each element with an id. """
        self.json_string = open(path).read()
        self.element_ids = []
        super().decode(self.json_string)
        return self.element_ids
    
    def interceptingJSONObject(self, s_and_end, *args):
        result = json.decoder.JSONObject(s_and_end, *args)
        if "id" in result[0]:
            self.element_ids.append(ElementId(self.posToLineCol(s_and_end[1]), self.posToLineCol(result[1]), result[0]["id"]))
        
        return result

    def posToLineCol(self, pos):
        line = self.json_string.count('\n', 0, pos) + 1
        col  = pos - self.json_string.rfind('\n', 0, pos)
        return (line, col)

class IgnoredIssues:
    """ Handle the ignored issues as defined in a YAML file. """

    def __init__(self, path = None):
        """ Initialize with a path to the ignored issues YAML file. """

        self.ignored_issues = None

        if path:
            with open(options.ignored_issues, "r") as f:
                self.ignored_issues = yaml.safe_load(f)
            if type(self.ignored_issues) != dict: # Empty file
                self.ignored_issues = None

    def selectResourceId(self, resource_id, file_type = None):
        """ Select a resource id from the YAML file to work on (if any). """
        self.resource_id         = resource_id
        self.issues_for_resource = {}
        self.element_ids         = []
        self.issues              = []
        if self.ignored_issues and resource_id in self.ignored_issues:
            if "ignored issues" in self.ignored_issues[resource_id]:
                self.issues_for_resource = self.ignored_issues[resource_id]["ignored issues"]
                if (file_type == "xml"):
                    self.element_ids = XMLElementIdMapper().parse(file_name)
                else:
                    self.element_ids = JSONElementIdMapper().parse(file_name)

    def hasForExpression(self, message, expression):
        """ Check if an ignored issues with the given message is defined for the given expression. """
        if expression in self.issues_for_resource:
            return self._checkIgnoredIssue(self.issues_for_resource[expression], message, expression)
        return False

    def hasForId(self, message, line, col):
        """ Check if an ignored issues with the given message is defined for the given element id, as represented by a
            line and column number. """
        element_id = None
        for element in self.element_ids:
            element_id = element.has(line, col)
            if element_id != False:
                break 

        if element_id and element_id in self.issues_for_resource:
            return self._checkIgnoredIssue(self.issues_for_resource[element_id], message, element_id)
        return False

    def finishSelectedId(self):
        """ Check if all issues have been processed. """

        for location in self.issues_for_resource:
            for issue in self.issues_for_resource[location]:
                if "handled" not in issue or not issue["handled"]:
                    self.issues.append(Issue("?", "?", "fatal", "An ignored issue was provided, but the issue didn't occur", location))

        return self.issues

    def _checkIgnoredIssue(self, ignored_issues, message, location):
        """ Check if an ignored issues with the given message is defined for the given expression or element id.
            If this is the case, the issue will be marked as "handled". """ 
        result = False

        for ignored_issue in ignored_issues:
            if "message" in ignored_issue and message.startswith(ignored_issue["message"]):
                if "reason" not in ignored_issue:
                    self.issues.append({
                        "line": "?",
                        "col": "?",
                        "severity": "fatal",
                        "text": "Issue ignored without providing a reason",
                        "expression": location
                    })
                result = True
                ignored_issue["handled"] = True

        return result

class ResourceIssues:
    """ Container for all the issues for a single FHIR resource. """
    
    def __init__(self, file_path, ignored_issues):
        """ Initialize the class.
            - file_path: the path to the resource file in xml or json (required)
            - ignored_issues: an optional IgnoredIssues instance
        """

        self.file_path = file_path

        # Get the id of the resource, if any
        if file_path.endswith(".xml"):
            resource_tree = ET.parse(file_path)
            try:
                self.id = resource_tree.find(".//f:id", ns).attrib["value"]
            except AttributeError:
                self.id = None
        elif file_path.endswith(".json"):
            resource_tree = json.load(open(file_path))
            if "id" in resource_tree:
                self.id = resource_tree["id"]

        self.issues = []
        self.ignored_issues = ignored_issues
        self.ignored_issues.selectResourceId(self.id, "xml" if file_path.endswith(".xml") else "json")

    def addIssue(self, line, col, severity, text, expression):
        """ Add the issue with the specified characteristics, unless it is listed in the ignored_issues. """
        if not severity in issue_levels:
            raise Exception(f"Unknown severity '{severity}' when validating file {self.file_path}")

        if not (self.ignored_issues.hasForExpression(text, expression) or self.ignored_issues.hasForId(text, line, col)):
            self.issues.append(Issue(line, col, severity, text, expression))

    def finish(self):
        """ Indicate that the check for the current resource is finished. """
        self.issues += self.ignored_issues.finishSelectedId()

if __name__ == "__main__":
    parser = OptionParser("usage: %prog [options] validator_result.xml")
    parser.add_option("-a", "--fail-at", type = "choice", choices = ["error", "warning", "information"], default = "error", 
        help="The level at which issues are considered fatal (error, warning or information). If issues at this level or more grave occur, this script will exit with a non-zero status.")
    parser.add_option("-v", "--verbosity-level", type = "choice", choices = ["error", "warning", "information"], default = "information",
        help="Only show issues at this level or lower (fatal, error, warning, information).")
    parser.add_option("-c", "--colorize", action = "store_true",
        help="Colorize the output.")
    parser.add_option("--github", action = "store_true",
        help="Output Github formatting marks.")
    parser.add_option("--ignored-issues", type="string",
        help="A YAML file with issues that should be ignored.")

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("Exactly one argument expected")

    fail_level      = issue_levels[options.fail_at]
    verbosity_level = issue_levels[options.verbosity_level]
    if fail_level > verbosity_level:
        parser.error("Chosen verbosity level would silence fatal issues")   

    if options.colorize:
        formatter = ColorFormatter(options.github)
    else:
        formatter = Formatter(options.github)

    ignored_issues = IgnoredIssues(options.ignored_issues)

    tree = ET.parse(args[0])
    ns = {"f": "http://hl7.org/fhir"}

    # Parse the Validator output, which will produce an OperationOutcome for each checked file (either a singele
    # OperationOutcome or a Bundle)
    issues = []
    if tree.getroot().tag == "{http://hl7.org/fhir}OperationOutcome":
        outcomes = [tree.getroot()]
    else:
        outcomes = tree.getroot().findall(".//f:OperationOutcome", ns)
   
    for outcome in outcomes:
        file_name = outcome.find("f:extension[@url='http://hl7.org/fhir/StructureDefinition/operationoutcome-file']/f:valueString", ns).attrib["value"]
        resource_issues = ResourceIssues(file_name, ignored_issues)

        for issue in outcome.findall("f:issue", ns):
            # Extract relevant information from the OperationOutcome
            try:
                text = issue.find("f:details/f:text", ns).attrib["value"]
            except AttributeError:
                text = "_No description_"

            element_id = None
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

            if not (severity == "information" and text == "All OK" and len(outcome.findall("f:issue", ns)) == 1): # When everything is ok, the Validator will output an "All OK" issue which we should ignore.
                resource_issues.addIssue(line, col, severity, text, expression)

        resource_issues.finish()
        issues.append(resource_issues)

    # Print out the results per file
    success = True
    for resource_issues in issues:
        if len(resource_issues.issues) > 0:
            id_str = "== " + resource_issues.file_path
            if resource_issues.id:
                id_str += f" ({resource_issues.id})"
            print(id_str)
            for issue in resource_issues.issues:
                if issue_levels[issue.severity] <= fail_level:
                    success = False
                if issue_levels[issue.severity] <= verbosity_level:
                    issue.print(formatter, resource_issues.file_path)
            id_str += formatter.RESET
            print()

    if not success:
        print(formatter.ERROR + "There were errors during validation" + formatter.RESET)
        sys.exit(1)
    print(formatter.OK + "All well" + formatter.RESET)
