# conf.py
# Map each service sublayer URL to its target in SDE as "FeatureDataset.FeatureClass"
# If there is NO feature dataset, you can just use "FeatureClass" (no dot).

SERVICE_TO_TARGET = {
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/0": "BC",
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/1": "DNPD",
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/2": "FPS",
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/3": "FRP",
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/4": "HPD",
    r"https://gis.ashghal.gov.qa/FSDMGP/rest/services/DNMC/FMPActiveProjects/MapServer/5": "RPD",
}

ALLOWED_EXTRA_IN_TARGET = {
    "created_user",
    "created_date",
    "last_edited_user",
    "shape.starea()",      # add
    "shape.stlength()",    # add
}