package main

import (
	"fmt"
)

const (
	averageMax = 200.0
	size       = 15
)

func main() {
	numbers := make(chan int)
	avg1 := make(chan float64)
	avg2 := make(chan float64)
	avg3 := make(chan float64)
	done := make(chan struct{})

	for i := 0; i <= 9; i++ {
		go sender(i, numbers)
	}

	go calculator(numbers, avg1, avg2, avg3)

	go receiver(1, avg1, done)
	go receiver(2, avg2, done)
	go receiver(3, avg3, done)

	<-done
	<-done
	<-done

	fmt.Println("Darbas baigtas.")
}

func sender(id int, out chan<- int) {
	i := id

	for {
		out <- i

		i = i*i - 4*i + 1
	}
}

func calculator(in <-chan int, out1, out2, out3 chan<- float64) {
	defer close(out1)
	defer close(out2)
	defer close(out3)

	values := make([]int, size)
	index := 0
	sum := 0

	for {
		number := <-in

		sum -= values[index]
		values[index] = number
		sum += number

		index = (index + 1) % size

		avg := float64(sum) / float64(size)

		if avg > averageMax {
			return
		}

		if avg < 10 {
			out1 <- avg
		}
		if avg >= 0 && avg <= 100 {
			out2 <- avg
		}
		if avg >= 75 && avg <= 200 {
			out3 <- avg
		}
	}
}

func receiver(id int, in <-chan float64, done chan<- struct{}) {
	defer func() {
		done <- struct{}{}
	}()

	for avg := range in {
		fmt.Printf("Gavejas %d gavo vidurki: %.2f\n", id, avg)
	}
}
