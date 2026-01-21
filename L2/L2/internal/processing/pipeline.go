package processing

import (
	"sort"

	"L2/internal/model"
)

func computePassesFunction(p model.VolleyballPlayer) bool {
	score := p.Winning * float64(p.Games)

	d := 0
	for i := 0; i < 900000000; i++ {
		d += i
	}

	return score >= 400.0
}

func passesFilter(p model.VolleyballPlayer) bool {
	return p.Winning >= 50.0
}

func DataManager(in <-chan model.VolleyballPlayer, req <-chan struct{}, get chan<- model.VolleyballPlayer, capacity int) {
	defer close(get)

	buffer := make([]model.VolleyballPlayer, 0, capacity)

	for {
		var inReadable <-chan model.VolleyballPlayer = in
		if len(buffer) >= capacity || in == nil {
			inReadable = nil
		}
		var reqReadable <-chan struct{} = req
		if len(buffer) == 0 {
			reqReadable = nil
		}

		if in == nil && len(buffer) == 0 {
			return
		}

		select {
		case p, ok := <-inReadable:
			if !ok {
				in = nil
				continue
			}
			if len(buffer) < capacity {
				buffer = append(buffer, p)
			}
		case <-reqReadable:
			item := buffer[0]
			copy(buffer[0:], buffer[1:])
			buffer = buffer[:len(buffer)-1]
			get <- item
		}
	}
}

func ResultManager(resIn <-chan model.VolleyballPlayer, finalOut chan<- []model.VolleyballPlayer) {
	defer close(finalOut)

	results := make([]model.VolleyballPlayer, 0, 40)

	for p := range resIn {
		i := sort.Search(len(results), func(i int) bool {
			return results[i].Winning >= p.Winning
		})
		results = append(results, model.VolleyballPlayer{})
		copy(results[i+1:], results[i:])
		results[i] = p
	}

	finalOut <- results
}

func Worker(req chan<- struct{}, get <-chan model.VolleyballPlayer, resIn chan<- model.VolleyballPlayer, done chan<- struct{}) {
	defer func() { done <- struct{}{} }()

	for {
		select {
		case req <- struct{}{}:
			p, ok := <-get
			if !ok {
				return
			}

			if computePassesFunction(p) && passesFilter(p) {
				resIn <- p
			}
		case p, ok := <-get:
			if !ok {
				return
			}

			if computePassesFunction(p) && passesFilter(p) {
				resIn <- p
			}
		}
	}
}
