""" class to analyse clustering of known de novos in genes according to their 
distances apart within the gene, and compare that to simulated de novo events 
within the same gene.
"""

from __future__ import division
from __future__ import print_function

import bisect
import itertools
import math
import operator
from functools import reduce

class AnalyseDeNovos(object):
    """ class to analyse clustering of de novo events via site specific 
    mutation rates
    """
    def __init__(self, transcript, site_weights, iterations):
        """ initialise the class
        """
        
        self.transcript = transcript
        self.site_weights = site_weights
        self.max_iter = iterations
    
    def analyse_missense(self, de_novo_events):
        """ analyse clustering of missense de novos
        """
        
        weights = self.site_weights.get_missense_rates_for_gene()
        return self.analyse_de_novos(de_novo_events, weights, self.max_iter)
    
    def analyse_nonsense(self, de_novo_events):
        """ analyse clustering of nonsense de novos
        """
        
        weights = self.site_weights.get_nonsense_rates_for_gene()
        return self.analyse_de_novos(de_novo_events, weights, self.max_iter)
    
    def analyse_functional(self, de_novo_events):
        """ analyse clustering of functional (missense and nonsense) de novos
        """
        
        weights = self.site_weights.get_functional_rates_for_gene()
        return self.analyse_de_novos(de_novo_events, weights, self.max_iter)
    
    def analyse_de_novos(self, de_novos, weights, iterations):
        """ find the probability of getting de novos with a mean conservation
        
        The probability is the number of simulations where the mean conservation
        between simulated de novos is less than the observed conservation.
        
        Args:
            de_novos: list of de novos within a gene
            weights: WeightedChoice object to randomly choose positions within
                a gene using site specific mutation rates.
            iterations: the (minimum) number of perumtations to run.
        
        Returns:
            mean conservation for the observed de novos and probability of 
            obtaining a mean conservation less than the observed conservation
        """
        
        if len(de_novos) < 2:
            return ("NA", "NA")
        
        minimum_prob = 1/(1 + iterations)
        sim_prob = minimum_prob
        dist = []
        
        cds_positions = self.convert_de_novos_to_cds_positions(de_novos)
        observed_value = self.get_score(cds_positions)
        
        # if the p-value that we obtain is right at the minimum edge of the 
        # simulated distribution, increase the number of iterations until the
        # p-value is no longer at the very edge (or we reach 100 million 
        # iterations).
        while iterations < 100000000 and sim_prob == minimum_prob:
            minimum_prob = 1/(1 + iterations)
            
            dist = self.simulate_distribution(weights, dist, len(de_novos), iterations)
            pos = bisect.bisect_right(dist, observed_value)
            sim_prob = (1 + pos)/(1 + len(dist))
            
            iterations += 1000000 # for if we need to run more iterations
        
        # output = open("/nfs/users/nfs_j/jm33/apps/mutation_rates/data/distribution.txt", "w")
        # for val in dist:
        #     output.write(str(val) + "\n")
        
        if type(observed_value) != "str":
            observed_value = "{0:0.1f}".format(observed_value)
        
        return (observed_value, sim_prob)
    
    def simulate_distribution(self, weights, dist=[], sample_n=2, max_iter=100):
        """ creates a distribution of mutation scores in a single gene
        
        Args:
            weights: WeightedChoice object
            dist: current list of simulated scores
            sample_n: number of de novo mutations to sample
            max_iter: number of iterations/simulations to run
        """
        
        # output = open("/nfs/users/nfs_j/jm33/apps/mutation_rates/data/sampled_sites.txt", "w")
        
        iteration = len(dist)
        while iteration < max_iter:
            iteration += 1
            
            positions = []
            while len(positions) < sample_n:
                site = weights.choice()
                positions.append(site)
                # chr_pos = self.transcript.get_position_on_chrom(site)
                # output.write(str(chr_pos) + "\n")
            
            # the following line is class specific - can do distance clustering,
            # conservation scores
            value = self.get_score(positions)
            dist.append(value)
        
        # output.close()
        
        dist.sort()
        
        return dist
    
    def convert_de_novos_to_cds_positions(self, de_novos):
        """ convert cds positions for de novo events into cds positions
        
        Args:
            de_novos: list of chrom bp positions within the transcript
        
        Returns:
            list of positions converted to CDS positions within the transcript
        """
        
        cds_positions = []
        for pos in de_novos:
            dist = self.transcript.convert_chr_pos_to_cds_positions(pos)
            cds_positions.append(dist)
        
        return cds_positions
        
    def product(self, iterable):
        """ get the product (multiplication sum) of a list of numbers
        """
        
        return reduce(operator.mul, iterable, 1)
    
    def geomean(self, values):
        """ get the geometric mean of a list of values
        """
        
        # get the geometric mean, but be careful around values of 0, since
        # without correction, the mean distance would be zero
        if 0 in values:
            # allow for 0s in a geometric mean by shifting everything up one, 
            # then dropping the mean by one at the end
            values = [x + 1 for x in values]
            total = self.product(values)
            mean = total ** (1/len(values))
            mean -= 1
        else:
            total = self.product(values)
            mean = total ** (1/len(values))
        
        return mean

