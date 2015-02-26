import numpy as np
from climlab.utils.thermo import blackbody_emission
from climlab.radiation.transmissivity import Transmissivity
from climlab.process.energy_budget import EnergyBudget

#  Renamed from NbandModel to Radiation
#  Now strictly atmospheric process
#  must be coupled to a surface model

class Radiation(EnergyBudget):
    '''Base class for all band radiation models,
    including grey and semi-grey model.
    
    Input argument absorptivity is band absorptivity
    (should same size as grid).
    
    By default emissivity = absorptivity.
    Subclasses can override this is necessary (e.g. for shortwave model)'''
    def __init__(self, absorptivity=None, albedo_sfc=0, **kwargs):
        super(Radiation, self).__init__(**kwargs)
        if absorptivity is None:
            absorptivity = np.zeros_like(self.Tatm)
        self.absorptivity = absorptivity
        self.albedo_sfc = albedo_sfc*np.ones_like(self.Ts)
        self.flux_from_space = np.zeros_like(self.Ts)
        self.flux_to_sfc = np.zeros_like(self.Ts)
        self.flux_from_sfc = np.zeros_like(self.Ts)
        self.flux_to_space = np.zeros_like(self.Ts)
        self.heating_rate['Ts'] = np.zeros_like(self.Ts)
        
    @property
    def absorptivity(self):
        return self.trans.absorptivity
    @absorptivity.setter
    def absorptivity(self, value):
        #  value should be a Field,
         #  or numpy array of same size as self.Tatm
        try:
            axis = value.domain.axis_index['lev']
        except:
            axis = self.Tatm.domain.axis_index['lev']
            # if a single scalar is given, broadcast that to all levels
            if len(np.shape(np.array(value))) is 0:
                value = np.ones_like(self.Tatm) * value
            elif value.shape != self.Tatm.shape:
                raise ValueError('absorptivity must be a Field, a scalar, or match atm grid dimensions')
        self.trans = Transmissivity(value, axis=axis)
    @property
    def emissivity(self):
        # This ensures that emissivity = absorptivity at all times
    #  needs to be overridden for shortwave classes
        return self.absorptivity
    @property
    def transmissivity(self):
        return self.trans.transmissivity
    @transmissivity.setter
    def transmissivity(self, value):
        self.absorptivity = 1 - value

    def compute_emission(self):
        return self.emissivity * blackbody_emission(self.Tatm)

    def radiative_heating(self):
        self.emission = self.compute_emission()
        #self.diagnostics['emission'] = emission
        try:
            fromspace = self.flux_from_space

        except:
            fromspace = np.zeros_like(self.Ts)
        
        self.flux_down = self.trans.flux_down(fromspace, self.emission)
        # this ensure same dimensions as other fields
        flux_down_sfc = self.flux_down[..., 0, np.newaxis]
        flux_up_bottom = self.flux_from_sfc + self.albedo_sfc*flux_down_sfc
        self.flux_up = self.trans.flux_up(flux_up_bottom, self.emission)
        self.flux_net = self.flux_up - self.flux_down
        flux_up_top = self.flux_up[..., -1, np.newaxis]
        # absorbed radiation (flux convergence) in W / m**2
        self.absorbed = -np.diff(self.flux_net)
        self.absorbed_total = np.sum(self.absorbed)
        self.heating_rate['Tatm'] = self.absorbed
        self.flux_to_sfc = flux_down_sfc
        self.flux_to_space = flux_up_top

    def _compute_heating_rates(self):
        '''Compute energy flux convergences to get heating rates in W / m**2.'''
        self.radiative_heating()        

    def flux_components_top(self):
        '''Compute the contributions to the outgoing flux to space due to
        emissions from each level and the surface.'''
        N = self.lev.size
        flux_up_bottom = self.flux_from_sfc
        emission = np.zeros_like(self.emission)
        this_flux_up = (np.ones_like(self.Ts) *
                        self.trans.flux_up(flux_up_bottom, emission))
        sfcComponent = this_flux_up[..., -1]
        atmComponents = np.zeros_like(self.Tatm)
        flux_up_bottom = np.zeros_like(self.Ts)
        # I'm sure there's a way to write this as a vectorized operation
        #  but the speed doesn't really matter if it's just for diagnostic
        #  and we are not calling it every timestep
        for n in range(N):
            emission = np.zeros_like(self.emission)
            emission[..., n] = self.emission[..., n]
            this_flux_up = self.trans.flux_up(flux_up_bottom, emission)
            atmComponents[..., n] = this_flux_up[..., -1]
        return sfcComponent, atmComponents

    def flux_components_bottom(self):
        '''Compute the contributions to the downwelling flux to surface due to
        emissions from each level.'''
        N = self.lev.size
        atmComponents = np.zeros_like(self.Tatm)
        flux_down_top = np.zeros_like(self.Ts)
        # I'm sure there's a way to write this as a vectorized operation
        #  but the speed doesn't really matter if it's just for diagnostic
        #  and we are not calling it every timestep
        for n in range(N):
            emission = np.zeros_like(self.emission)
            emission[..., n] = self.emission[..., n]
            this_flux_down = self.trans.flux_down(flux_down_top, emission)
            atmComponents[..., n] = this_flux_down[..., 0]
        return atmComponents


class RadiationSW(Radiation):
    '''Emissivity is always set to zero for shortwave classes.'''
    @property
    def emissivity(self):
        # This ensures that emissivity is always zero for shortwave classes
        return np.zeros_like(self.absorptivity)
    