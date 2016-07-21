#include <random>
#include <vector>
#include <chrono>
#include <algorithm>
#include <python2.7/Python.h>

#include "weighted_choice.h"
// g++ -std=c++0x -c -fPIC weighted_choice.cpp -o weighted_choice.o
// g++ -shared -Wl,-soname,libchooser.so -o libchooser.so weighted_choice.o

Chooser::Chooser() {
    /**
        Constructor for Chooser class
    */
    
    // start the random sampler
    long long random_seed = std::chrono::system_clock::now().time_since_epoch().count();
    generator.seed(random_seed);
}

void Chooser::add_choice(int site, double prob, char ref, char alt) {
     /**
        adds another choice to the class object
        
        @site site position (e.g. 100001)
        @prob site mutation rate (e.g. 0.000000005)
        @ref reference allele for site e.g. 'A'
        @alt alternate allele for site e.g. 'T'
    */
    
    // keep track of the cumulative sum for each added site
    double cumulative_sum = get_summed_rate() + prob;
    cumulative.push_back(cumulative_sum);
    
    sites.push_back(AlleleChoice {site, ref, alt, prob});
    
    // any time we add another choice, reset the sampler, so we can sample
    // from all the possible entries.
    std::uniform_real_distribution<double> temp(0.0, cumulative_sum);
    dist = temp;
}

AlleleChoice Chooser::choice() {
    /**
        chooses a random element using a set of probability weights
        
        @returns AlleleChoice struct containing the pos, ref and alt
    */
    
    if (cumulative.empty()) {
        return AlleleChoice {-1, 'N', 'N', 0.0};
    }
    
    // get a random float between 0 and the cumulative sum
    double number = dist(generator);
    
    // figure out where in the list a random probability would fall
    std::vector<double>::iterator pos;
    pos = std::lower_bound(cumulative.begin(), cumulative.end(), number);
    int offset = pos - cumulative.begin();
    
    return sites[offset];
}

double Chooser::get_summed_rate() {
    /**
        gets the cumulative sum for all the current choices.
    */
    
    if (sites.empty()) {
        return 0.0;
    } else {
        return cumulative.back();
    }
}
