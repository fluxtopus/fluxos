declare module 'js-yaml' {
  export interface LoadOptions {
    filename?: string;
    schema?: any;
    onWarning?: (e: any) => void;
    json?: boolean;
  }

  export interface DumpOptions {
    indent?: number;
    skipInvalid?: boolean;
    flowLevel?: number;
    styles?: Record<string, any>;
    schema?: any;
    sortKeys?: boolean | ((a: any, b: any) => number);
    lineWidth?: number;
    noRefs?: boolean;
    noCompatMode?: boolean;
    condenseFlow?: boolean;
  }

  export function load(str: string, opts?: LoadOptions): any;
  export function dump(obj: any, opts?: DumpOptions): string;

  const _default: {
    load: typeof load;
    dump: typeof dump;
  };

  export default _default;
}

