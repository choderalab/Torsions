import pymc
import TorsionScanSet
from chemistry.topologyobjects import DihedralType
import numpy as np


class TorsionFitModel(object):
    """pymc model

    Attributes:
    ----------
    pymc_parameters: dict() of pymc parameters
    parameters_to_optimize: list of tuples (dihedrals to optimize)
    fags: list of TorsionScanSet for fragments

    """

    def __init__(self, param, stream, frags):

        self.pymc_parameters = dict()
        self.frags = frags

        multiplicities = [1, 2, 3, 4, 6]
        multiplicity_bitstrings = dict()
        self.parameters_to_optimize = TorsionScanSet.to_optimize(param, stream)
        for p in self.parameters_to_optimize:
            torsion_name = p[0]+'_'+p[1]+'_'+p[2]+'_'+p[3]
            if torsion_name not in multiplicity_bitstrings.keys():
                multiplicity_bitstrings[torsion_name] = 0

            for m in multiplicities:
                name = p[0]+'_'+p[1]+'_'+p[2]+'_'+p[3]+'_' + str(m) + '_K'
                k = pymc.Uniform(name, lower=0, upper=20, value=0)
                for i in range(len(param.dihedral_types[p])):
                    if param.dihedral_types[p][i].per == m:
                        multiplicity_bitstrings[torsion_name] += 2**(m-1)
                        k = pymc.Uniform(name, lower=0, upper=20, value=param.dihedral_types[p][i].phi_k)
                        break

                self.pymc_parameters[name] = k

                name = p[0]+'_'+p[1]+'_'+p[2]+'_'+p[3]+'_' + str(m) + '_Phase'
                phase = pymc.DiscreteUniform(name, lower=0, upper=1, value=0)
                for i in range(len(param.dihedral_types[p])):
                    if param.dihedral_types[p][i].per == m:
                        if param.dihedral_types[p][i].phase == 0:
                            phase = pymc.DiscreteUniform(name, lower=0, upper=1, value=0)
                            break
                        if param.dihedral_types[p][i].phase == 3.141592653589793:
                            phase = pymc.DiscreteUniform(name, lower=0, upper=1, value=1)
                            break

                self.pymc_parameters[name] = phase

        for torsion_name in multiplicity_bitstrings.keys():
            name = torsion_name + '_multiplicity_bitstring'
            bitstring = pymc.DiscreteUniform(name, lower=0, upper=63, value=multiplicity_bitstrings[torsion_name])
            self.pymc_parameters[name] = bitstring

        self.pymc_parameters['log_sigma'] = pymc.Uniform('log_sigma', lower=-10, upper=0, value=np.log(0.01))
        self.pymc_parameters['sigma'] = pymc.Lambda('sigma',
                                                    lambda log_sigma=self.pymc_parameters['log_sigma']: np.exp(log_sigma))
        self.pymc_parameters['precision'] = pymc.Lambda('precision',
                                                        lambda log_sigma=self.pymc_parameters['log_sigma']: np.exp(-2*log_sigma))

        @pymc.deterministic
        def mm_potential(pymc_parameters=self.pymc_parameters, param=param):
            self.update_param(param)
            mm_energy = np.ndarray(0)
            for frag in self.frags:
                frag.compute_energy(param)
                mm_energy = np.append(mm_energy, frag.mm_energy)
            return mm_energy

        size = [len(i.mm_energy) for i in self.frags]
        qm_potential = np.ndarray(0)
        for i in range(len(frags)):
            qm_potential=np.append(qm_potential, frags[i].qm_energy)
        self.pymc_parameters['mm_potential'] = mm_potential
        self.pymc_parameters['qm_fit'] = pymc.Normal('qm_fit', mu=self.pymc_parameters['mm_potential'],
                                                     tau=self.pymc_parameters['precision'], size=size, observed=True,
                                                     value=qm_potential)

    def add_missing(self, param):
        """
        Update param set with missing multiplicities.

        :param: chemistry.charmm.CharmmParameterSet

        :return: updated CharmmParameterSet with multiplicities 1-6 for parameters to optimize
        """
        multiplicities = [1, 2, 3, 4, 6]
        for p in self.parameters_to_optimize:
            per = []
            for i in range(len(param.dihedral_types[p])):
                per.append(param.dihedral_types[p][i].per)
            for j in multiplicities:
                if j not in per:
                    param.dihedral_types[p].append(DihedralType(0, j, 0))

    def update_param(self, param):
        """
        Update param set based on current pymc model parameters.

        :param: chemistry.charmm.CharmmParameterSet

        :return: updated CharmmParmaterSet based on current TorsionFitModel parameters
        """
        multiplicities = [1, 2, 3, 4, 6]
        for p in self.parameters_to_optimize:
            torsion_name = p[0]+'_'+p[1]+'_'+p[2]+'_'+p[3]
            multiplicity_bitstring = self.pymc_parameters[torsion_name + '_multiplicity_bitstring'].value

            for i in range(len(param.dihedral_types[p])):
                m = int(param.dihedral_types[p][i].per)
                multiplicity_bitmask = 2**(m-1) # multiplicity bitmask
                if multiplicity_bitstring & multiplicity_bitmask:
                    if m == 5:
                        continue
                    k = torsion_name + '_' + str(m) + '_K'
                    phase = torsion_name + '_' + str(m) + '_Phase'
                    pymc_variable = self.pymc_parameters[k]
                    param.dihedral_types[p][i].phi_k = pymc_variable.value
                    pymc_variable = self.pymc_parameters[phase]
                    param.dihedral_types[p][i].phase = pymc_variable.value
                else:
                    # This torsion periodicity is disabled.
                    param.dihedral_types[p][i].phi_k = 0





