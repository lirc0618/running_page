import { ComponentType } from 'react';

type SvgComponent = {
  default: ComponentType<any>;
};

const FailedLoadSvg = () => <div>Failed to load SVG</div>;

export const loadSvgComponent = async (
  stats: Record<string, () => Promise<unknown>>,
  path: string
): Promise<SvgComponent> => {
  try {
    const imported = await stats[path]();
    // Vite's glob with `import: 'ReactComponent'` resolves directly to the
    // component function. Keep support for the full SVGR module shape too.
    const module = imported as { ReactComponent?: ComponentType<any> };
    const component =
      typeof imported === 'function' ? imported : module.ReactComponent;
    if (!component) throw new Error(`SVG component export missing for ${path}`);
    return { default: component };
  } catch (error) {
    console.error(error);
    return { default: FailedLoadSvg };
  }
};
