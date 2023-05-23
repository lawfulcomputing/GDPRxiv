Issue tracker is **ONLY** used for reporting bugs. New features should be discussed on our slack channel. Please use [stackoverflow](https://stackoverflow.com) for supporting issues.

## Expected Behavior
The DPA was expected to get the docs from the source: {{host}}{{start_path}}

## Current Behavior
The docs, of the DPA in question, is no longer reachable due to changes in the html source structure.

## Possible Solution
To reflect the changes of the html source structure in the DPA's source code, human analysis is needed.
**Take a look at the *failed* XPath sample tests to get an idea of what element needs to get changed.**

## Steps to Reproduce
1. Get instance of gdpr class.
2. Get instance of dpa class for eu member: {{country}}.
3. Check if important dpa html elements are reachable through service.
4. Given the reachability output from step 3., check if there's any reachability_flag set to 0 for any of the XPaths.
5. Lastly, following step 4., if there's a reachability_flag set to 0, the dpa cannot get the docs.

## Context (Environment)
Python Version:  {{major}}.{{minor}}.{{micro}}
Platform:        {{system}}, {{release}}

## Detailed Description
#### XPath sample tests:
{{tests}}

#### DPA source code:
{{permalink}}

#### Learn more:
**What is XPath?**
> XPath can be used to navigate through elements and attributes in an XML document. XPath uses path expressions to select nodes or node-sets in an XML document. These path expressions look very much like the path expressions you use with traditional computer file systems.
> Source: [w3schools](https://www.w3schools.com/xml/xpath_intro.asp)

We use XPath to sample test if certain elements are reachable from the DPA's html source structure. If important elements are no longer reachable, the source code of the DPA will not be able to get the docs.

## Possible Implementation
