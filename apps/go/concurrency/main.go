package main

import (
	"context"
	"sync"

	"github.com/aws/aws-lambda-go/lambda"
)

type Request struct {
	Tasks int `json:"tasks"`
}

type Response struct {
	CompletedTasks int `json:"completed_tasks"`
}

func handler(ctx context.Context, req Request) (Response, error) {
	tasks := req.Tasks
	if tasks <= 0 {
		tasks = 5000 // Quantidade padrão de goroutines
	}

	var wg sync.WaitGroup
	var mu sync.Mutex
	counter := 0

	for i := 0; i < tasks; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			// Simula um pequeno atraso/trabalho
			calc := 0.0
			for j := 0; j < 1000; j++ {
				calc += 1.0
			}
			mu.Lock()
			counter++
			mu.Unlock()
		}()
	}

	wg.Wait()

	return Response{CompletedTasks: counter}, nil
}

func main() {
	lambda.Start(handler)
}
