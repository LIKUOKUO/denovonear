""" Script to investigate the probability of multiple mutations clustering 
within a single gene.
"""

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import sys
import os
import argparse

from src.interval import Interval
from src.get_transcript_sequences import GetTranscriptSequence
from src.load_mutation_rates import load_trincleotide_mutation_rates
from src.load_known_de_novos import load_known_de_novos
from src.load_conservation_scores import load_conservation_scores
from src.site_specific_rates import SiteRates
from src.analyse_de_novo_clustering import AnalyseDeNovoClustering
from src.analyse_de_novo_conservation import AnalyseDeNovoConservation


def get_options():
    """ get the command line switches
    """
    
    parser = argparse.ArgumentParser(description='examine mutation clustering in genes')
    parser.add_argument("--in", dest="input", help="input filename for file listing known mutations in genes")
    parser.add_argument("--out", dest="output", help="output filename")
    parser.add_argument("--rates", dest="mut_rates", help="mutation rates filename")
    parser.add_argument("--deprecated-genes", dest="deprecated_genes", help="deprecated gene IDs filename")

    args = parser.parse_args()
    
    return args.input, args.output, args.mut_rates, args.deprecated_genes

def get_deprecated_gene_ids(filename):
    """ gets a dict of the gene IDs used during in DDD datasets that have been 
    deprecated in favour of other gene IDs
    """
    
    deprecated = {}
    with open(filename) as f:
        for line in f:
            line = line.strip().split()
            old = line[0]
            new = line[1]
            deprecated[old] = new
    
    return deprecated

def identify_transcript(ensembl, transcript_ids):
    """ for a given HGNC ID, finds the transcript with the longest CDS
    
    Args:
        ensembl: GetTranscriptSequence object to request sequences and data 
            from the ensembl REST API
        transcript_ids: list of transcript IDs for a single gene
    
    Returns:
        the transcript ID of the longest protein coding transcript in the list
    """
    
    transcripts = {}
    for transcript_id in transcript_ids:
        # get the transcript's protein sequence via the ensembl REST API
        seq = ensembl.get_protein_seq_for_transcript(transcript_id)
        
        # ignore transcripts without protein sequence
        if seq == "Sequence unavailable":
            continue
        
        transcripts[len(seq)] = transcript_id
    
    return transcripts

def construct_gene_object(ensembl, transcript_id):
    """ creates and Interval object for a gene from ensembl databases
    """
    
    print("loading features and sequence")
    # get the sequence for the identified transcript
    (chrom, start, end, strand, genomic_sequence) = ensembl.get_genomic_seq_for_transcript(transcript_id, expand=10)
    cds_sequence = ensembl.get_cds_seq_for_transcript(transcript_id)
    
    # get the locations of the exons and cds from ensembl
    cds_ranges = ensembl.get_cds_ranges_for_transcript(transcript_id)
    exon_ranges = ensembl.get_exon_ranges_for_transcript(transcript_id)
    
    # start an interval object with the locations and sequence
    transcript = Interval(transcript_id, start, end, strand, chrom, exon_ranges, cds_ranges)
    transcript.add_cds_sequence(cds_sequence)
    transcript.add_genomic_sequence(genomic_sequence, offset=10)
    
    return transcript

def check_denovos_in_gene(transcript, de_novos):
    """ make sure that all the  de novos occur in the loaded gene
    """
    
    for pos in de_novos:
        # convert the de novo positions to cds positions, which raises an error
        # if the position is not in the CDS exons
        try:   
            transcript.convert_chr_pos_to_cds_positions(pos)
        except ValueError:
            return False
    
    return True

def load_gene(ensembl, gene_id, de_novos):
    """ sort out all the necessary sequences and positions for a gene
    
    Args:
        ensembl: GetTranscriptSequence object to request data from ensembl
        gene_id: HGNC symbol for gene
        de_novos: list of de novo positions, so we can check they all fit in 
            the gene transcript
        
    Returns:
        Interval object for gene, including genomic ranges and sequences
    """
    
    print("loading transcript ID")
    ensembl_genes = ensembl.get_genes_for_hgnc_id(gene_id)
    transcript_ids = ensembl.get_transcript_ids_for_ensembl_gene_ids(ensembl_genes, gene_id)
    transcripts = identify_transcript(ensembl, transcript_ids)
    
    # start with the longest transcript
    lengths = sorted(transcripts)[::-1]
    transcript_id = transcripts[lengths[0]]
    
    # TODO: allow for genes without any coding sequence.
    if transcript_id == {}:
        raise ValueError(gene_id + " lacks coding transcripts")
    
    try:
        transcript = construct_gene_object(ensembl, transcript_id)
    except ValueError:
        # some genes raise errors when loading the gene sequence e.g. CCDC18
        transcript_id = transcripts[lengths[1]]
        transcript = construct_gene_object(ensembl, transcript_id)
    
    # create a Interval object using the longest transcript, but if that 
    # transcript doesn't contain all the de novo positions, run through the 
    # alternate transcripts in order of length (allows for CSMD2 variant 
    # chr1:34071484 and PHACTR1 chr6:12933929).
    pos = 0
    while not check_denovos_in_gene(transcript, de_novos) and pos < (len(transcripts) - 1):
        pos += 1
        transcript_id = transcripts[sorted(transcripts)[::-1][pos]]
        transcript = construct_gene_object(ensembl, transcript_id)
    
    # raise an IndexError if we can't get a transcript that contains all de 
    # novos. eg ZFN467 with chr7:149462931 and chr7:149461727 which are on
    # mutually exclusive transcripts
    if not check_denovos_in_gene(transcript, de_novos):
        raise IndexError(gene_id + " de novos aren't in CDS sequence")
    
    # make sure we have the gene location for loading the conservation scores
    chrom = transcript.get_chrom()
    start = transcript.get_start()
    end = transcript.get_end()
    
    # print("loading conservation scores")
    # # add in phyloP conservation scores
    # conservation_scores = load_conservation_scores(CONSERVATION_FOLDER, chrom, start, end)
    # try:
    #     transcript.add_conservation_scores(conservation_scores)
    # except ValueError:
    #     pass
    
    return transcript

def main():
    
    input_file, output_file, mut_rates_file, deprecated_gene_id_file = get_options()
    
    # load all the data
    ensembl = GetTranscriptSequence()
    mut_dict = load_trincleotide_mutation_rates(mut_rates_file)
    old_gene_ids = get_deprecated_gene_ids(deprecated_gene_id_file)
    known_de_novos = load_known_de_novos(input_file)
    
    output = open(output_file, "w")
    output.write("\t".join(["gene_id", \
        "missense_events_n", "missense_dist", "missense_probability", 
        "nonsense_events_n", "nonsense_distance", "nonsense_dist_probability"]) + "\n")
    
    initial_iterations = 1000000
    for gene_id in known_de_novos:
        iterations = initial_iterations
        # gene_id = "SMARCA2"
        print(gene_id)
        
        func_events = known_de_novos[gene_id]["functional"]
        missense_events = known_de_novos[gene_id]["missense"]
        nonsense_events = known_de_novos[gene_id]["nonsense"]
        
        # don't analyse genes with only one de novo functional mutation
        if len(func_events) < 2:
            continue
        
        # fix HGNC IDs that have been discontinued in favour of other gene IDs
        if gene_id in old_gene_ids:
            gene_id = old_gene_ids[gene_id]
        
        try:
            transcript = load_gene(ensembl, gene_id, func_events)
        except IndexError:
            continue
        
        site_weights = SiteRates(transcript, mut_dict)
        
        print("simulating clustering")
        probs = AnalyseDeNovoClustering(transcript, site_weights, iterations)
        
        # (func_dist, func_prob) = probs.analyse_functional(func_events)
        (miss_dist, miss_prob) = probs.analyse_missense(missense_events)
        (nons_dist, nons_prob) = probs.analyse_nonsense(nonsense_events)
        
        # [cons_func, cons_func_p, cons_miss, cons_miss_p, cons_nons, \
        #     cons_nons_p] = ["NA"] * 6
        # if hasattr(transcript, "conservation_scores"):
        #     probs = AnalyseDeNovoConservation(transcript, site_weights, iterations)
            
        #     # (cons_func, cons_func_p) = probs.analyse_functional(func_events)
        #     (cons_miss, cons_miss_p) = probs.analyse_missense(missense_events)
        #     (cons_nons, cons_nons_p) = probs.analyse_nonsense(nonsense_events)
        
        # output.write("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\t{7}\t{8}\t{9}\t{10}\n".\
        #     format(gene_id, \
        #     len(missense_events), miss_dist, miss_prob, cons_miss, cons_miss_p, \
        #     len(nonsense_events), nons_dist, nons_prob, cons_nons, cons_nons_p ))
        
        output.write("{0}\t{1}\t{2}\t{3}\t{4}\t{5}\t{6}\n".format(gene_id, \
            len(missense_events), miss_dist, miss_prob, \
            len(nonsense_events), nons_dist, nons_prob ))
        
        # sys.exit()
    
if __name__ == '__main__':
    main()




