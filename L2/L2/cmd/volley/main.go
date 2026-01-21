package main

import (
	"fmt"
	"os"

	"L2/internal/files"
	"L2/internal/model"
	"L2/internal/processing"
)

func main() {
	inPath := "IFF3_1_JakutonisA_L1_dat_1.json"
	outPath := "IFF3_JakutonisA_L2_rez.txt"

	data, err := files.ReadJSON(inPath)
	if err != nil {
		fmt.Println("read error:", err)
		os.Exit(1)
	}

	n := len(data.Player)
	if n == 0 {
		fmt.Println("no input data")
		return
	}

	workers := n / 4
	if workers < 2 {
		workers = 2
	}

	capacity := n / 4
	if capacity < 1 {
		capacity = 1
	}

	inCh := make(chan model.VolleyballPlayer)       // main -> data manager (insert)
	reqCh := make(chan struct{})                    // worker -> data manager (request)
	getCh := make(chan model.VolleyballPlayer)      // data manager -> worker (grant)
	resIn := make(chan model.VolleyballPlayer)      // worker -> result manager
	finalOut := make(chan []model.VolleyballPlayer) // result manager -> main
	workerDone := make(chan struct{})               // worker when job is done

	go processing.DataManager(inCh, reqCh, getCh, capacity)
	go processing.ResultManager(resIn, finalOut)

	for i := 0; i < workers; i++ {
		go processing.Worker(reqCh, getCh, resIn, workerDone)
	}

	for i := range data.Player {
		inCh <- data.Player[i]
	}
	close(inCh)

	for i := 0; i < workers; i++ {
		<-workerDone
	}
	close(resIn)

	results := <-finalOut

	if err := files.WriteResults(outPath, data.Player, results); err != nil {
		fmt.Println("write error:", err)
		os.Exit(1)
	}

	fmt.Printf("OK: %d įrašų, darbininkai=%d, buferis=%d\nRezultatai: %s\n",
		n, workers, capacity, outPath)
}
