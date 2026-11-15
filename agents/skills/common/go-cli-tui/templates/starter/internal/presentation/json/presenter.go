package json

import (
	"encoding/json"
	"os"

	"{{ .ModulePath }}/internal/presentation/errors"
)

type Presenter struct{}

func NewPresenter() *Presenter {
	return &Presenter{}
}

func (p *Presenter) RenderSuccess(data interface{}) error {
	env := errors.ResponseEnvelope{
		OK:   true,
		Data: data,
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(env)
}
