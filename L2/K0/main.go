package main

import (
	"fmt"
)

const size = 100

func main() {
	idTransfer := make(chan int)
	arrayTransfer := make(chan []int)
	done := make(chan struct{})

	for i := 1; i <= 4; i++ {
		go sender(i, idTransfer)
	}

	go controller(idTransfer, arrayTransfer)

	go printer(arrayTransfer, done)

	<-done

	fmt.Println("Darbas baigtas.")
}

func sender(id int, sendID chan<- int) {
	for {
		sendID <- id
	}
}

func controller(getID <-chan int, sendArray chan<- []int) {
	defer close(sendArray)

	arrayIds := make([]int, size)
	left := 0
	right := size - 1
	count := 0

	for count < size {
		id := <-getID

		if id < 3 {
			if left <= right {
				arrayIds[left] = id
				left++
				count++
			}
		} else {
			if left <= right {
				arrayIds[right] = id
				right--
				count++
			}
		}

		if count%10 == 0 {
			copyArr := make([]int, size)
			copy(copyArr, arrayIds)
			sendArray <- copyArr
		}
	}
}

func printer(getArray <-chan []int, done chan<- struct{}) {
	defer func() {
		done <- struct{}{}
	}()

	for arrayIds := range getArray {
		fmt.Print("Masyvo turinys: ")
		for i, v := range arrayIds {
			if i > 0 {
				fmt.Print(", ")
			}
			fmt.Print(v)
		}
		fmt.Println("\n")
	}
}
