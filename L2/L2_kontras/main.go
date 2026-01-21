package main

import (
	"fmt"
)

// total amount of numbers that have to go through the receiver
const totalNumbers = 20

func main() {
	// main -> receiver
	numbers := make(chan int)

	// receiver -> printers
	evenCh := make(chan int)
	oddCh := make(chan int)

	// synchronisation
	doneReceiver := make(chan struct{})
	donePrinters := make(chan struct{}, 2)

	// stop senders
	stopSenders := make(chan struct{})

	printLock := make(chan struct{}, 1)
	printLock <- struct{}{}

	go sender(0, numbers, stopSenders)
	go sender(11, numbers, stopSenders)

	go receiver(numbers, evenCh, oddCh, totalNumbers, doneReceiver, stopSenders)

	go printer("Lyginių skaičių spausdintojas", evenCh, donePrinters, printLock)
	go printer("Nelyginių skaičių spausdintojas", oddCh, donePrinters, printLock)

	<-doneReceiver

	<-donePrinters
	<-donePrinters

	fmt.Println("Darbas baigtas.")
}

func sender(start int, out chan<- int, stop <-chan struct{}) {
	i := 0
	for {
		select {
		case <-stop:
			return
		case out <- (start + i):
			i++
		}
	}
}

func receiver(numbers <-chan int, evenCh, oddCh chan<- int,
	total int, doneReceiver chan<- struct{}, stopSenders chan<- struct{},
) {
	for i := 0; i < total; i++ {
		x := <-numbers
		if x%2 == 0 {
			evenCh <- x
		} else {
			oddCh <- x
		}
	}

	close(evenCh)
	close(oddCh)
	close(stopSenders)

	doneReceiver <- struct{}{}
}

func printer(name string, in <-chan int, done chan<- struct{}, printLock chan struct{}) {
	var nums []int
	for x := range in {
		nums = append(nums, x)
	}

	<-printLock

	fmt.Println(name)
	fmt.Println("------------------------------")
	fmt.Printf("Iš viso gauta skaičių: %d\n", len(nums))
	fmt.Print("Masyvo turinys: ")
	for i, v := range nums {
		if i > 0 {
			fmt.Print(", ")
		}
		fmt.Print(v)
	}
	fmt.Println("\n")

	printLock <- struct{}{}

	done <- struct{}{}
}
