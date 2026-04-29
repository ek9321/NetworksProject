My goal is to construct an integrated network model linking OIM transmission lines and substations to ERCOT generators and settlement nodes. This would allow us to connect physical infrastructure (lines and substations), generation assets, and LMPs within a unified topology.

Because naming conventions differ across datasets, this requires systematic fuzzy matching across substation names, generator interconnection points, and settlement node identifiers. Once likely matches are identified, we can use geographic proximity and network consistency constraints to “snap” components together.

For example, if a small town contains a single OIM substation and a single ERCOT settlement node, we can infer correspondence even if the labels differ. We then validate matches using spatial distance thresholds and network structure consistency.
