""" get weight gene mutation rates
"""

from denovonear.weights import WeightedChoice

def get_codon_info(transcript, bp, boundary_dist):
    """ get the details of the codon which a variant resides in
    
    Args:
        transcript: Transcript object for a gene
        bp: nucleotide position of the variant (within the transcript gene range)
        boundary_dist: distance in base-pairs to the nearest exon boundary.
    
    Returns:
        dictionary of codon sequence, cds position, amino acid that the codon
        translates to, and position within the codon.
    """
    
    # get the distances to the closest exon boundaries
    exon_start, exon_end = transcript.find_closest_exon(bp)
    in_coding = transcript.in_coding_region(bp)
    
    # ignore positions outside the exons that are too distant from a boundary
    if boundary_dist >= 9 and not in_coding:
        raise IndexError
    
    cds_pos = transcript.chrom_pos_to_cds(bp)
    if in_coding:
        codon_number = transcript.get_codon_number_for_cds_position(cds_pos)
        intra_codon = transcript.get_position_within_codon(cds_pos)
        codon_seq = transcript.get_codon_sequence(codon_number)
        initial_aa = transcript.translate(codon_seq)
    else:
        codon_number = None
        intra_codon = None
        codon_seq = None
        initial_aa = None
    
    return {"cds_pos": cds_pos, "codon_seq": codon_seq, "intra_codon": intra_codon,
         "codon_number": codon_number, "initial_aa": initial_aa}

def get_boundary_distance(transcript, bp):
    """ get the distance in bp for a variant to the nearest exon boundary
    
    Args:
        transcript: Transcript object for a gene
        bp: nucleotide position of the variant (within the transcript gene range)
    
    Returns:
        distance in base-pairs to the nearest exon boundary.
    """
    
    exon_start, exon_end = transcript.find_closest_exon(bp)
    distance = min(abs(exon_start - bp), abs(exon_end - bp))
    
    # sites within the coding region are actually one bp further away,
    # since we are measuring the distance to the base inside the exon
    # boundary
    if transcript.in_coding_region(bp):
        distance += 1
    
    return distance

def get_gene_range(transcript):
    """ get the lowest and highest positions of a transcripts coding sequence
    
    Args:
        transcript: Transcript object for a gene.
    
    Returns:
        tuple of start and end coordinates
    """
    
    boundary_1 = transcript.get_cds_start()
    boundary_2 = transcript.get_cds_end()
    
    start = min(boundary_1, boundary_2)
    end = max(boundary_1, boundary_2)
    
    # shift the end position out by one, to use in python ranges
    end += 1
    
    return (start, end)

def get_mutated_aa(transcript, base, codon, intra_codon):
    """ find the amino acid resulting from a base change to a codon
    
    Args:
        transcript: Transcript object for a gene
        base: alternate base (e.g. 'G') to introduce
        codon: DNA sequence of a single codon
        intra_codon: position within the codon to be altered (0-based)
    
    Returns:
        single character amino acid code translated from the altered codon.
    """
      
    # figure out what the mutated codon is
    mutated_codon = list(codon)
    mutated_codon[intra_codon] = base
    mutated_codon = "".join(mutated_codon)
    
    return transcript.translate(mutated_codon)

class SiteRates(object):
    """ class to build weighted choice random samplers for nonsense, missense,
    and functional classes of variants, using site specific mutation rates
    
    Only include the site specific probability if it mutates to a different
    amino acid, or occurs close to an intron/exon boundary, using consequences
    defined at: http://www.ensembl.org/info/genome/variation/predicted_data.html
    """
    
    bases = set(["A", "C", "G", "T"])
    categories = ["missense", "nonsense", "synonymous", "splice_lof",
        "splice_region", "loss_of_function"]
    transdict = {"A": "T", "T": "A", "G": "C", "C": "G"}
    
    def __init__(self, gene, mut_dict, masked_sites=None):
        
        self.gene = gene
        self.mut_dict = mut_dict
        self.masked = masked_sites
        
        self.rates = {}
        for cq in self.categories:
            self.rates[cq] = WeightedChoice()
        
        for bp in range(*get_gene_range(self.gene)):
            self.check_position(bp)
    
    def __getitem__(self, category):
        """ get site-specific mutation rates for each CDS base
        
        Args:
            category: string to indicate the consequence type. The permitted
                types are "missense", "nonsense", "synonymous",
                "loss_of_function", "splice_lof", and "splice_region".
        
        Returns:
            A WeightedChoice object for the CDS, where each position is paired
            with its mutation rate. We can then randomly sample sites from the
            CDS WeightedChoice object according to the probability of each site
            being mutated to the specific consequence type.
        """
        
        return self.rates[category]
    
    def splice_lof_check(self, initial_aa, mutated_aa, position):
        """ checks if a variant has a splice_donor or splice_acceptor consequence
        
        These variants are defined as being the two intronic base-pairs adjacent
        to the intron/exon boundary.
        """
        
        return (not self.gene.in_coding_region(position)) and self.boundary_dist < 3
    
    def nonsense_check(self, initial_aa, mutated_aa, position):
        """ checks if two amino acids are a nonsense (eg stop_gained) mutation
        """
        
        return initial_aa != "*" and mutated_aa == "*"
    
    def missense_check(self, initial_aa, mutated_aa, position):
        """ checks if two amino acids are a missense mutation (but not nonsense)
        """
        
        # trim out nonsense mutations such as stop_gained mutations, and splice
        # site mutations
        if self.nonsense_check(initial_aa, mutated_aa, position) or \
                self.splice_lof_check(initial_aa, mutated_aa, position):
            return False
        
        # include the site if it mutates to a different amino acid.
        return initial_aa != mutated_aa
    
    def splice_region_check(self, initial_aa, mutated_aa, position):
        """ checks if a variant has a splice_region consequence, but not
        splice_donor or splice_acceptor
        """
        
        if self.splice_lof_check(initial_aa, mutated_aa, position) or \
                initial_aa != mutated_aa:
            return False
        
        # catch splice region variants within the exon, and in the appropriate
        # region of the intron (note that loss of function splice_donor and
        # splice_acceptor variants have been excluded when we trimmed nonsense).
        if self.gene.in_coding_region(position):
            # check for splice_region_variant inside exon
            return self.boundary_dist < 4
        else:
            # check for splice_region_variant inside intron
            return self.boundary_dist < 9
    
    def synonymous_check(self, initial_aa, mutated_aa, position):
        """ checks if two amino acids are synonymous
        """
        
        return not self.nonsense_check(initial_aa, mutated_aa, position) \
            and not self.splice_lof_check(initial_aa, mutated_aa, position) \
            and not self.missense_check(initial_aa, mutated_aa, position) \
            and not self.splice_region_check(initial_aa, mutated_aa, position)
    
    def check_position(self, bp):
        """ add the consequence specific rates for the alternates for a variant
        
        Args:
            bp: genomic position of the variant
        """
        
        # ignore sites within masked regions (typically masked because the
        # site has been picked up on alternative transcript)
        if self.masked is not None and self.masked.in_coding_region(bp):
            return None
        
        # ignore sites outside the CDS region
        if bp < min(self.gene.get_cds_start(), self.gene.get_cds_end()) or \
            bp > max(self.gene.get_cds_start(), self.gene.get_cds_end()):
            return None
        
        seq = self.gene.get_trinucleotide(bp)
        self.boundary_dist = get_boundary_distance(self.gene, bp)
        
        if self.gene.get_strand() == "-":
            seq = self.gene.reverse_complement(seq)
        
        try:
            codon = get_codon_info(self.gene, bp, self.boundary_dist)
        except IndexError:
            return None
        
        initial_aa = codon["initial_aa"]
        cds_pos = codon["cds_pos"]
        
        # drop the initial base, since we want to mutate to other bases
        for base in self.bases - set(seq[1]):
            mutated_aa = initial_aa
            alt_base = seq[0] + base + seq[2]
            rate = self.mut_dict[seq][alt_base]
            if initial_aa is not None:
                mutated_aa = get_mutated_aa(self.gene, base, codon["codon_seq"], codon["intra_codon"])
            
            if self.nonsense_check(initial_aa, mutated_aa, bp):
                category = "nonsense"
            elif self.splice_lof_check(initial_aa, mutated_aa, bp):
                category = "splice_lof"
            elif self.missense_check(initial_aa, mutated_aa, bp):
                category = "missense"
            elif self.splice_region_check(initial_aa, mutated_aa, bp):
                category = "splice_region"
            elif self.synonymous_check(initial_aa, mutated_aa, bp):
                category = "synonymous"
            
            # figure out what the ref and alt alleles are, with respect to
            # the + strand.
            ref_base = seq[1]
            alt = base
            if self.gene.get_strand() == "-":
                ref_base = self.transdict[ref_base]
                alt = self.transdict[alt]
            self.rates[category].add_choice(cds_pos, rate, ref_base, alt)
            
            if category in ["nonsense", "splice_lof"]:
                self.rates["loss_of_function"].add_choice(cds_pos, rate, ref_base, alt)
