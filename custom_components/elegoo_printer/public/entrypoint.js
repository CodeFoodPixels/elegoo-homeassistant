import "https://unpkg.com/wired-card@2.1.0/lib/wired-card.js?module";
import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class ElegooFrontend extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      route: { type: Object },
      panel: { type: Object },
    };
  }

  render() {
    return html`
      <iframe src="${this.panel.config.elegoo.url}" />
    `;
  }

  static get styles() {
    return css`
      iframe {
        width: 100vw;
        height: 100vh;
        border: 0px;
      }
    `;
  }
}
customElements.define("elegoo-frontend", ElegooFrontend);
const styleEl = document.createElement("style");
styleEl.innerHTML = `
body {
  margin: 0;
  padding: 0;
  height: 100vh;
  font-size: 0;
}
`;
document.head.appendChild(styleEl);