import os
from pygdpr.models.dpa.ireland import *
from pygdpr.models.dpa.united_kingdom import *
from pygdpr.models.dpa.austria import *
from pygdpr.models.dpa.belgium import *
from pygdpr.models.dpa.bulgaria import *
from pygdpr.models.dpa.czech_republic import *
from pygdpr.models.dpa.croatia import *
from pygdpr.models.dpa.cyprus import *
from pygdpr.models.dpa.denmark import *
from pygdpr.models.dpa.estonia import *
from pygdpr.models.dpa.france import *
from pygdpr.models.dpa.hungary import *
from pygdpr.models.dpa.latvia import *
from pygdpr.models.dpa.germany import *
from pygdpr.models.dpa.greece import *
from pygdpr.models.dpa.finland import *
from pygdpr.models.dpa.italy import *
from pygdpr.models.dpa.luxembourg import *
from pygdpr.models.dpa.malta import *
from pygdpr.models.dpa.portugal import *
from pygdpr.models.dpa.slovenia import *
from pygdpr.models.dpa.spain import*
from pygdpr.models.dpa.lithuania import *
from pygdpr.models.dpa.netherlands import *
from pygdpr.models.dpa.poland import *
from pygdpr.models.dpa.edpb import *
from pygdpr.models.dpa.romania import *
from pygdpr.models.dpa.slovakia import *
from pygdpr.models.dpa.sweden import *


path = "/lithuania"
dpa = Lithuania(path)
dpa.get_docs_Guidelines()

#path = "/germany"
#dpa = Germany(path)
#dpa.get_docs()

#path = "/france"
#dpa = France(path)
#dpa.get_docs_reports()


#path = "/sweden"
#dpa = Sweden(path)
#dpa.get_docs()