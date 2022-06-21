#!/usr/bin/env python3

import json, os, re, sys, yaml
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
    
    def print(self, formatter):
        if self.severity in ["fatal", "error"]:
            color = formatter.ERROR
        elif self.severity == "warning":
            color = formatter.WARNING
        else:
            color = formatter.INFORMATION
        out =  f"  -  {color}{self.severity}{formatter.RESET} at {self.expression} ({self.line}, {self.col}):\n"
        out += f"     {self.text}"
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
        self.load(path)
    
    def load(self, path = None):
        if path:
            for ignored_issues in yaml.safe_load_all(open(path)):
                if self.ignored_issues == None:
                    self.ignored_issues = {}

                require_occurence = True
                if "issues should occur" in ignored_issues:
                    if not ignored_issues["issues should occur"]:
                        require_occurence = False
                    ignored_issues.pop("issues should occur")

                # The ignored issues are organized similarly to how the YAML file is defined. After processing, it looks
                # like:
                # {
                #     regex for resource id: {
                #         regex for location: [
                #             {
                #                 message: The message being suppressed
                #                 reason: Reason why the message is suppressed
                #                 handled: True when the message did actually occur in the output
                #                 key: The original resource identifier in the YAML file, before it was turned into a regex
                #             }
                #         ]
                #     }
                # }
                for resource_id in ignored_issues:
                    if "ignored issues" in ignored_issues[resource_id]:
                        if require_occurence and resource_id.find("*") != -1:
                            print(formatter.ERROR + "Wildcards were used to suppress an error on multiple resources, but this is only allowed for errors that aren't required to occur!" + formatter.RESET)
                            sys.exit(1)

                        resource_regex = self._wildcardToRegex(resource_id)
                        issues_for_resource = self.ignored_issues[resource_regex] if resource_regex in self.ignored_issues else {}

                        for path_id in ignored_issues[resource_id]["ignored issues"]:
                            path_regex = self._wildcardToRegex(path_id)
                            issues_for_path = issues_for_resource[path_regex] if path_regex in issues_for_resource else []
                            for issue in ignored_issues[resource_id]["ignored issues"][path_id]:
                                issue["handled"]           = False
                                issue["require_occurence"] = require_occurence
                                issues_for_path.append(issue)
                            issues_for_resource[path_regex] = issues_for_path
                        self.ignored_issues[resource_regex] = issues_for_resource
        
    def selectResourceId(self, resource_id, file_path, file_type = None):
        """ Select a resource id from the YAML file to work on (if any). """
        self.resource_id         = resource_id
        self.issues_for_resource = {}
        self.element_ids         = []
        self.issues              = []
        
        if self.ignored_issues:
            for resource_regex in self.ignored_issues:
                matchResult = False
                if resource_id is not None:
                    matchResult = resource_regex.match(resource_id) or resource_regex.match(file_path) 
                else:
                    matchResult = resource_regex.match(file_path)

                if matchResult:
                    self.issues_for_resource.update(self.ignored_issues[resource_regex])
                    if (file_type == "xml"):
                        self.element_ids = XMLElementIdMapper().parse(file_name)
                    else:
                        self.element_ids = JSONElementIdMapper().parse(file_name)

    def hasForExpression(self, message, expression):
        """ Check if an ignored issues with the given message is defined for the given expression. """
        return self._checkIgnoredIssue(message, expression)

    def hasForId(self, message, line, col):
        """ Check if an ignored issues with the given message is defined for the given element id, as represented by a
            line and column number. """
        element_id = None
        for element in self.element_ids:
            element_id = element.has(line, col)
            if element_id != False:
                break 

        if element_id:
            return self._checkIgnoredIssue(message, element_id)
        return False

    def finishSelectedId(self):
        """ Check if all issues have been processed. This only takes into account the issues that were defined with a
            full resource id, without wildcards. """

        for issues_per_path in self.issues_for_resource.values():
            for issue in issues_per_path:
                if not issue["handled"] and issue["require_occurence"]:
                    self.issues.append(Issue("?", "?", "fatal", "An ignored issue was provided, but the issue didn't occur", self.resource_id))
        
        return self.issues

    def _checkIgnoredIssue(self, message, location):
        """ Check if an ignored issues with the given message is defined for the given expression or element id.
            If this is the case, the issue will be marked as "handled". """ 
        result = False

        for regex in self.issues_for_resource.keys():
            if regex.match(location):
                for ignored_issue in self.issues_for_resource[regex]:
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
    
    def _wildcardToRegex(self, wildcard_string):
        return re.compile("^" + wildcard_string.replace(".", "\.").replace("*", ".*?").replace("[", "\[").replace("]", "\]") + "$", re.MULTILINE)

class ResourceIssues:
    """ Container for all the issues for a single FHIR resource. """
    
    def __init__(self, file_path, ignored_issues):
        """ Initialize the class.
            - file_path: the path to the resource file in xml or json (required)
            - ignored_issues: an optional IgnoredIssues instance
        """

        self.file_path = file_path

        file_type = None
        if file_path.lower().endswith(".xml"):
            file_type = "xml"
        elif file_path.lower().endswith(".json"):
            file_type = "json"

        # Get the id of the resource, if any
        self.id = None
        if file_type == "xml":
            resource_tree = ET.parse(file_path)
            try:
                self.id = resource_tree.find(".//f:id", ns).attrib["value"]
            except AttributeError:
                self.id = None
        elif file_type == "json":
            resource_tree = json.load(open(file_path))
            if "id" in resource_tree:
                self.id = resource_tree["id"]

        self.issues = []
        self.ignored_issues = ignored_issues
        self.ignored_issues.selectResourceId(self.id, file_path, file_type)

    def addIssue(self, line, col, severity, text, expression):
        """ Add the issue with the specified characteristics, unless it is listed in the ignored_issues. """
        if not severity in issue_levels:
            raise Exception(f"Unknown severity '{severity}' when validating file {self.file_path}")

        if not (self.ignored_issues.hasForExpression(text, expression) or self.ignored_issues.hasForId(text, line, col)):
            self.issues.append(Issue(line, col, severity, text, expression))

    def count(self, issue_severity):
        return len([issue for issue in self.issues if issue.severity == issue_severity])

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
    parser.add_option("--stats-file", type = "string",
        help="Write statistics to the following JSON file.")
    parser.add_option("--ignored-issues", type="string", action = "append",
        help="A YAML file with issues that should be ignored. Issues defined here should actually be encountered.")

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("Exactly one argument expected")

    fail_level      = issue_levels[options.fail_at]
    verbosity_level = issue_levels[options.verbosity_level]
    if fail_level > verbosity_level:
        parser.error("Chosen verbosity level would silence fatal issues")   

    if options.colorize:
        formatter = ColorFormatter()
    else:
        formatter = Formatter()

    ignored_issues = IgnoredIssues()
    if options.ignored_issues is not None:
        for ignored_issues_file in options.ignored_issues:
            ignored_issues.load(ignored_issues_file)

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
    num_issues = {}
    for severity in issue_levels.keys():
        num_issues[severity] = 0

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
                    issue.print(formatter)
            id_str += formatter.RESET
            print()
        for severity in issue_levels.keys():
            num_issues[severity] += resource_issues.count(severity)

    stats = ""
    for severity in issue_levels.keys():
        if num_issues[severity] > 0:
            stats += f"- {num_issues[severity]} {severity} messages\n"
    if stats != "":
        print("+++ Statistics +++")
        print(stats)
    if options.stats_file:
        with open(options.stats_file, "w") as f:
            json.dump(num_issues, f)

    if not success:
        print(formatter.ERROR + "There were errors below your threshold!" + formatter.RESET)
        sys.exit(1)
    print(formatter.OK + "All well" + formatter.RESET)
