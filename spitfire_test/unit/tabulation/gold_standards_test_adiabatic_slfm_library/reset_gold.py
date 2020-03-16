from spitfire.chemistry.mechanism import ChemicalMechanismSpec
from spitfire.chemistry.tabulation import build_adiabatic_slfm_library
import spitfire.chemistry.analysis as sca
import numpy as np

m = ChemicalMechanismSpec(cantera_xml='h2-burke.xml', group_name='h2-burke')
pressure = 101325.
air = m.stream(stp_air=True)
air.TP = 1200., pressure
fuel = m.stream('TPY', (300., pressure, 'H2:1'))

flamelet_specs = {'mech_spec': m, 'pressure': pressure,
                  'oxy_stream': air, 'fuel_stream': fuel,
                  'grid_points': 34}

l = build_adiabatic_slfm_library(flamelet_specs, diss_rate_values=np.logspace(0, 1, 8), verbose=False)
l = sca.compute_specific_enthalpy(m, l)

l.save_to_file('library_gold.pkl')
