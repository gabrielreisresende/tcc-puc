package main

import (
	"context"
	"math"

	"github.com/aws/aws-lambda-go/lambda"
)

type Request struct {
	Number int64 `json:"number"`
}

type Response struct {
	Factors []int64 `json:"factors"`
}

func primeFactors(n int64) []int64 {
	var factors []int64
	for n%2 == 0 {
		factors = append(factors, 2)
		n = n / 2
	}
	for i := int64(3); i <= int64(math.Sqrt(float64(n))); i = i + 2 {
		for n%i == 0 {
			factors = append(factors, i)
			n = n / i
		}
	}
	if n > 2 {
		factors = append(factors, n)
	}
	return factors
}

func handler(ctx context.Context, req Request) (Response, error) {
	num := req.Number
	if num <= 1 {
		// Número padrão grande para forçar o processamento da CPU
		num = 999999999989
	}
	return Response{Factors: primeFactors(num)}, nil
}

func main() {
	lambda.Start(handler)
}
